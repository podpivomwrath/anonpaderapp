"""Ежедневные задания, стрики, награды за вход (патч 23).

Аналог services/trial_service.py: условия слушают события боя, перемещения,
событий мира, трофеев, продажи скупщику и PvP, обновляют character_dailies.
День и стрики считаются по ДАТАМ в московской зоне (не по таймерам) —
ensure_day_rollover сравнивает last_login_date с "сегодня" и идемпотентно
(один раз в день) выдаёт новые задания, продвигает 14-дневный цикл входа и
проверяет пропуски. Вызывается из services.onboarding_service.get_character
на каждое действие игрока — реальная работа происходит не чаще раза в день.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import DailyQuestDef, load_daily_quests
from game.economy import dailies_config as dc
from models import Character, CharacterDaily, CharacterStats, CharacterTitle
from services import elixir_service, experience_service, trophy_service, wallet_service

_TZ = ZoneInfo(dc.DAILY_RESET_TZ)
_rng = random.Random()

_defs_by_id: dict[str, DailyQuestDef] | None = None


def _load() -> None:
    global _defs_by_id
    if _defs_by_id is not None:
        return
    _defs_by_id = {q.id: q for q in load_daily_quests()}


def quest_def(quest_id: str) -> DailyQuestDef | None:
    _load()
    return _defs_by_id.get(quest_id)


def _eligible_pool(character: Character) -> list[DailyQuestDef]:
    _load()
    return [q for q in _defs_by_id.values() if character.level >= q.min_level]


def today_msk(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(_TZ).date()


def seconds_until_reset(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    now_msk = now.astimezone(_TZ)
    next_midnight = datetime.combine(now_msk.date() + timedelta(days=1), time.min, tzinfo=_TZ)
    return int((next_midnight - now_msk).total_seconds())


# --- Выдача наград (золото/самоцветы/эликсиры/титул) ---


async def _grant_reward(db: AsyncSession, character: Character, reward: dict) -> list[str]:
    lines: list[str] = []
    if "gold" in reward:
        await wallet_service.deposit(db, character.id, "farm", reward["gold"])
        lines.append(f"{reward['gold']} золота")
    if "gems" in reward:
        await wallet_service.deposit(db, character.id, "donate", reward["gems"])
        lines.append(f"💎 {reward['gems']} Пепельных самоцветов")
    if "elixir" in reward:
        elixir_id, count = reward["elixir"]
        edef = elixir_service.elixir_def(elixir_id)
        if edef is not None:
            await elixir_service.grant(db, character.id, elixir_id, count)
            lines.append(f"{edef.emoji} {edef.name} ×{count}")
    if "elixirs_random_combat" in reward:
        n = min(reward["elixirs_random_combat"], len(dc.COMBAT_ELIXIR_POOL))
        for elixir_id in _rng.sample(dc.COMBAT_ELIXIR_POOL, n):
            edef = elixir_service.elixir_def(elixir_id)
            if edef is None:
                continue
            await elixir_service.grant(db, character.id, elixir_id, 2)
            lines.append(f"{edef.emoji} {edef.name} ×2")
    if "title" in reward:
        await _unlock_title(db, character, reward["title"])
        lines.append(f"титул «{dc.TITLE_NAMES.get(reward['title'], reward['title'])}»")
    return lines


async def _unlock_title(db: AsyncSession, character: Character, title_id: str) -> None:
    existing = await db.scalar(
        select(CharacterTitle).where(
            CharacterTitle.character_id == character.id, CharacterTitle.title_id == title_id,
        )
    )
    if existing is None:
        db.add(CharacterTitle(character_id=character.id, title_id=title_id))
    if character.active_title_id is None:
        character.active_title_id = title_id


def title_name(character: Character) -> str | None:
    if character.active_title_id is None:
        return None
    return dc.TITLE_NAMES.get(character.active_title_id)


# --- Назначение ежедневок ---


async def _assign_new_dailies(db: AsyncSession, character: Character, today: date) -> None:
    already = await db.scalar(
        select(func.count()).select_from(CharacterDaily).where(
            CharacterDaily.character_id == character.id, CharacterDaily.date == today,
        )
    )
    if already:
        return
    pool = _eligible_pool(character)
    chosen = _rng.sample(pool, min(dc.DAILY_QUEST_COUNT, len(pool)))
    for qdef in chosen:
        db.add(CharacterDaily(character_id=character.id, quest_id=qdef.id, progress=0, completed=False, date=today))
    await db.flush()


# --- Сброс дня + стрики (вызывается из onboarding_service.get_character) ---


@dataclass
class DayRolloverNotice:
    lines: list[str] = field(default_factory=list)


async def ensure_day_rollover(
    db: AsyncSession, character: Character, now: datetime | None = None,
) -> DayRolloverNotice | None:
    now = now or datetime.now(timezone.utc)
    today = today_msk(now)
    if character.last_login_date == today:
        return None  # уже обработано сегодня — самый частый случай

    lines: list[str] = []
    gap = None if character.last_login_date is None else (today - character.last_login_date).days

    if gap is None or gap > 1:
        if character.login_streak > 0:
            lines.append("📅 Ты не приходил вчера. Списки не ждут — стрик обнулён.")
        character.login_streak = 1
        character.login_cycle_day = 1
    else:  # gap == 1 — пришёл на следующий день подряд
        character.login_streak += 1
        character.login_cycle_day = character.login_cycle_day % dc.LOGIN_CYCLE_LENGTH + 1

    if character.daily_streak > 0:
        daily_gap = None if character.last_daily_completed_date is None else (
            today - character.last_daily_completed_date
        ).days
        if daily_gap is None or daily_gap > 1:
            character.daily_streak = 0

    character.last_login_date = today

    cycle_reward = dc.LOGIN_CYCLE_REWARDS.get(character.login_cycle_day)
    if cycle_reward is not None:
        reward_lines = await _grant_reward(db, character, cycle_reward)
        lines.append(
            f"📅 День {character.login_streak} подряд. Пепельные Земли отмечают упорных.\n"
            f"Получено: {', '.join(reward_lines)}\n"
            f"Стрик входа: {character.login_streak} дней"
        )

    await _assign_new_dailies(db, character, today)
    await db.flush()
    return DayRolloverNotice(lines=lines) if lines else None


# --- Прогресс заданий ---


async def _active_dailies(db: AsyncSession, character: Character) -> list[CharacterDaily]:
    today = today_msk()
    rows = (
        await db.scalars(
            select(CharacterDaily).where(
                CharacterDaily.character_id == character.id,
                CharacterDaily.date == today,
                CharacterDaily.completed.is_(False),
            )
        )
    ).all()
    return list(rows)


@dataclass
class DailyCompletion:
    quest_title: str
    xp: int
    gold: int
    levels_gained: int
    new_level: int


@dataclass
class DailyProgressResult:
    completed: list[DailyCompletion] = field(default_factory=list)
    streak_notice: str | None = None


async def _apply_delta(
    db: AsyncSession, character: Character, row: CharacterDaily, delta: int,
) -> DailyCompletion | None:
    if delta <= 0 or row.completed:
        return None
    qdef = quest_def(row.quest_id)
    if qdef is None:
        return None
    target = dc.scaled_target(qdef.base_target, character.level)
    row.progress = min(row.progress + delta, target)
    if row.progress < target:
        return None
    row.completed = True
    xp, gold = dc.daily_reward(character.level)
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    levelup = experience_service.add_experience(character, stats, xp)
    await wallet_service.deposit(db, character.id, "farm", gold)
    return DailyCompletion(
        quest_title=qdef.title, xp=xp, gold=gold,
        levels_gained=levelup.levels_gained, new_level=levelup.new_level,
    )


async def _finish(
    db: AsyncSession, character: Character, completions: list[DailyCompletion],
) -> DailyProgressResult:
    if not completions:
        return DailyProgressResult()
    today = today_msk()
    notice = None
    if character.last_daily_completed_date != today:
        character.last_daily_completed_date = today
        character.daily_streak += 1
        milestone = dc.STREAK_MILESTONES.get(character.daily_streak)
        if milestone is not None:
            reward_lines = await _grant_reward(db, character, milestone)
            notice = (
                f"🔥 Стрик ежедневок: {character.daily_streak} дней!\n"
                f"Получено: {', '.join(reward_lines)}"
            )
    await db.flush()
    return DailyProgressResult(completed=completions, streak_notice=notice)


async def record_battle(db: AsyncSession, character: Character, report) -> DailyProgressResult:
    """Вызывать после КАЖДОЙ победы в PvE (services/encounter_service.py)."""
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is None:
            continue
        delta = 0
        if qdef.condition_type == "kill_any":
            delta = int(report.won)
        elif qdef.condition_type == "kill_deep_ring":
            delta = int(report.won and report.mob_level >= character.level)
        elif qdef.condition_type == "skill_only_win":
            delta = int(report.won and report.only_skills)
        elif qdef.condition_type == "kill_streak_no_rest":
            delta = int(report.won)
        elif qdef.condition_type == "low_hp_survive":
            delta = int(report.won and report.hp_min_pct * 100 < 25)
        if delta:
            completion = await _apply_delta(db, character, row, delta)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


async def record_defeat(db: AsyncSession, character: Character) -> None:
    """Поражение сбрасывает «убить подряд без отдыха» (патч 23, «Выносливость»)."""
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "kill_streak_no_rest":
            row.progress = 0


async def record_rest(db: AsyncSession, character: Character) -> None:
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "kill_streak_no_rest":
            row.progress = 0


async def record_trophies(
    db: AsyncSession, character: Character, trophies: dict[str, int],
) -> DailyProgressResult:
    if not trophies:
        return DailyProgressResult()
    rare_ids = {t.id for t in trophy_service.trophy_defs_ordered() if t.id != "ash_dust"}
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is None:
            continue
        if qdef.condition_type == "trophy_any":
            amount = sum(trophies.values())
        elif qdef.condition_type == "trophy_rare":
            amount = sum(v for k, v in trophies.items() if k in rare_ids)
        else:
            continue
        if amount <= 0:
            continue
        completion = await _apply_delta(db, character, row, amount)
        if completion:
            completions.append(completion)
    return await _finish(db, character, completions)


async def record_cell_moved(db: AsyncSession, character: Character) -> DailyProgressResult:
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "cells_moved":
            completion = await _apply_delta(db, character, row, 1)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


async def record_exploration(db: AsyncSession, character: Character) -> DailyProgressResult:
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "explorations":
            completion = await _apply_delta(db, character, row, 1)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


async def record_event_choice(db: AsyncSession, character: Character) -> DailyProgressResult:
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "event_choices":
            completion = await _apply_delta(db, character, row, 1)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


async def record_sell_gold(db: AsyncSession, character: Character, gold: int) -> DailyProgressResult:
    if gold <= 0:
        return DailyProgressResult()
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "sell_gold":
            completion = await _apply_delta(db, character, row, gold)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


async def record_pvp_win(db: AsyncSession, character: Character) -> DailyProgressResult:
    completions = []
    for row in await _active_dailies(db, character):
        qdef = quest_def(row.quest_id)
        if qdef is not None and qdef.condition_type == "pvp_win":
            completion = await _apply_delta(db, character, row, 1)
            if completion:
                completions.append(completion)
    return await _finish(db, character, completions)


# --- Чтение состояния (чат /ежедневки, мини-апп) ---


@dataclass
class DailyQuestState:
    quest_id: str
    title: str
    progress_label: str
    progress: int
    target: int
    completed: bool
    xp_reward: int
    gold_reward: int


@dataclass
class DailiesOverview:
    quests: list[DailyQuestState]
    daily_streak: int
    next_milestone_day: int | None
    next_milestone_reward: dict | None
    seconds_until_reset: int


async def get_dailies_overview(
    db: AsyncSession, character: Character, now: datetime | None = None,
) -> DailiesOverview:
    today = today_msk(now)
    rows = (
        await db.scalars(
            select(CharacterDaily)
            .where(CharacterDaily.character_id == character.id, CharacterDaily.date == today)
            .order_by(CharacterDaily.id)
        )
    ).all()
    xp, gold = dc.daily_reward(character.level)
    quests = []
    for row in rows:
        qdef = quest_def(row.quest_id)
        if qdef is None:
            continue
        target = dc.scaled_target(qdef.base_target, character.level)
        quests.append(
            DailyQuestState(
                quest_id=qdef.id, title=qdef.title, progress_label=qdef.progress_label,
                progress=min(row.progress, target), target=target, completed=row.completed,
                xp_reward=xp, gold_reward=gold,
            )
        )
    next_day = next((d for d in sorted(dc.STREAK_MILESTONES) if d > character.daily_streak), None)
    return DailiesOverview(
        quests=quests,
        daily_streak=character.daily_streak,
        next_milestone_day=next_day,
        next_milestone_reward=dc.STREAK_MILESTONES.get(next_day) if next_day else None,
        seconds_until_reset=seconds_until_reset(now),
    )


@dataclass
class LoginCycleState:
    login_streak: int
    cycle_day: int
    cycle_length: int
    today_reward: dict | None
    claimed_today: bool
    rewards: dict[int, dict]


async def get_login_state(
    db: AsyncSession, character: Character, now: datetime | None = None,
) -> LoginCycleState:
    return LoginCycleState(
        login_streak=character.login_streak,
        cycle_day=character.login_cycle_day,
        cycle_length=dc.LOGIN_CYCLE_LENGTH,
        today_reward=dc.LOGIN_CYCLE_REWARDS.get(character.login_cycle_day),
        claimed_today=character.last_login_date == today_msk(now),
        rewards=dc.LOGIN_CYCLE_REWARDS,
    )
