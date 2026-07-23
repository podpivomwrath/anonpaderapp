"""Трекер классовых испытаний (патч 12): условия слушают события боя,
перемещения, событий мира и добычи трофеев, обновляют character_trial_progress
и при достижении цели разблокируют бафф в character_unlocked_buffs — навсегда,
даже будущий полный ресет класса эту запись не трогает (см. патч 12, п.5).

Испытания каждого подкласса независимы (без цепочки, "все сразу") — активные
для персонажа это все ЕЩЁ НЕ завершённые испытания его текущего character.subclass.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat.battle_report import ELEMENT_SKILLS, BattleReport
from game.content_loader import ClassTrialDef, load_class_trials
from models import Character, CharacterTrialProgress, CharacterUnlockedBuff

_defs_by_id: dict[str, ClassTrialDef] | None = None
_defs_by_subclass: dict[str, list[ClassTrialDef]] | None = None


def _load() -> None:
    global _defs_by_id, _defs_by_subclass
    if _defs_by_id is not None:
        return
    all_defs = load_class_trials()
    _defs_by_id = {t.id: t for t in all_defs}
    _defs_by_subclass = {}
    for t in all_defs:
        _defs_by_subclass.setdefault(t.subclass, []).append(t)


def trial_defs_for(subclass: str) -> list[ClassTrialDef]:
    _load()
    return _defs_by_subclass.get(subclass, [])


def trial_def(trial_id: str) -> ClassTrialDef | None:
    _load()
    return _defs_by_id.get(trial_id)


async def _progress_rows(
    db: AsyncSession, character_id: int, trial_ids: list[str]
) -> dict[str, CharacterTrialProgress]:
    if not trial_ids:
        return {}
    rows = (
        await db.scalars(
            select(CharacterTrialProgress).where(
                CharacterTrialProgress.character_id == character_id,
                CharacterTrialProgress.trial_id.in_(trial_ids),
            )
        )
    ).all()
    return {r.trial_id: r for r in rows}


async def _get_or_create(db: AsyncSession, character_id: int, trial_id: str) -> CharacterTrialProgress:
    row = await db.scalar(
        select(CharacterTrialProgress).where(
            CharacterTrialProgress.character_id == character_id,
            CharacterTrialProgress.trial_id == trial_id,
        )
    )
    if row is None:
        row = CharacterTrialProgress(character_id=character_id, trial_id=trial_id, progress=0, completed=False)
        db.add(row)
        await db.flush()
    return row


async def _unlock_buff(db: AsyncSession, character_id: int, buff_id: str) -> None:
    existing = await db.scalar(
        select(CharacterUnlockedBuff).where(
            CharacterUnlockedBuff.character_id == character_id,
            CharacterUnlockedBuff.buff_id == buff_id,
        )
    )
    if existing is None:
        db.add(CharacterUnlockedBuff(character_id=character_id, buff_id=buff_id))


async def _apply_delta(
    db: AsyncSession, character_id: int, trial: ClassTrialDef, delta: int
) -> str | None:
    """+delta прогресса; при достижении цели — разблокирует бафф и возвращает
    его id (для уведомления), иначе None. Завершённые испытания не трогает."""
    if delta <= 0:
        return None
    row = await _get_or_create(db, character_id, trial.id)
    if row.completed:
        return None
    target = trial.params.get("count", 1)
    row.progress = min(row.progress + delta, target)
    if row.progress >= target:
        row.completed = True
        await _unlock_buff(db, character_id, trial.buff_id)
        return trial.buff_id
    return None


async def _reset(db: AsyncSession, character_id: int, trial: ClassTrialDef) -> None:
    row = await _get_or_create(db, character_id, trial.id)
    if not row.completed:
        row.progress = 0


async def _active_trials(db: AsyncSession, character: Character) -> list[ClassTrialDef]:
    if character.subclass is None:
        return []
    defs = trial_defs_for(character.subclass)
    rows = await _progress_rows(db, character.id, [d.id for d in defs])
    return [d for d in defs if not (rows.get(d.id) is not None and rows[d.id].completed)]


def _battle_delta(condition_type: str, params: dict, report: BattleReport, character: Character) -> int:
    won = report.won
    if condition_type == "defeat_higher_level":
        return int(won and report.mob_level > character.level)
    if condition_type == "win_min_turns":
        return int(won and report.turns >= params["turns"])
    if condition_type in ("kill_in_max_turns", "kill_count_max_turns_each"):
        return int(won and report.turns <= params["turns"])
    if condition_type == "survive_hp_floor":
        return int(won and report.hp_min_pct * 100 < params["hp_floor_pct"])
    if condition_type == "win_count_never_below_hp":
        return int(won and report.hp_min_pct * 100 >= params["hp_floor_pct"])
    if condition_type == "win_count_dropped_below_hp":
        return int(won and report.hp_min_pct * 100 <= params["hp_ceiling_pct"])
    if condition_type == "win_no_hp_below_single":
        return int(won and report.hp_min_pct * 100 >= params["hp_floor_pct"])
    if condition_type in ("win_start_hp_below_single", "win_count_start_hp_below", "win_streak_start_hp_below"):
        return int(won and report.start_hp_pct * 100 < params["hp_ceiling_pct"])
    if condition_type == "win_damage_taken_exceeds_maxhp":
        return int(won and report.total_damage_taken > report.max_hp)
    if condition_type == "kill_count_in_ring":
        return int(won and params["ring_min"] <= report.mob_level <= params["ring_max"])
    if condition_type in ("win_count_control_each_fight", "win_count_freeze_each_fight"):
        return int(won and report.control_landed >= 1)
    if condition_type == "win_count_no_crit_taken":
        return int(won and not report.crit_taken)
    if condition_type == "win_count_no_hit_taken":
        return int(won and report.hits_taken == 0)
    if condition_type == "win_count_basic_attack_only":
        return int(won and report.only_basic_attack)
    if condition_type == "win_count_skills_only":
        return int(won and report.only_skills)
    if condition_type == "win_count_debuff_skill_each_fight":
        return int(won and report.debuff_skill_used)
    if condition_type == "win_streak_no_rest":
        return int(won)
    if condition_type == "crit_count":
        return report.crits_dealt
    if condition_type in ("control_success_count", "control_freeze_count"):
        return report.control_landed
    if condition_type == "skill_combo_streak_count":
        return report.skill_combo_streak_count
    if condition_type == "all_elements_in_fight_count":
        return int(report.all_elements_used)
    if condition_type == "consecutive_crits_in_fight":
        return int(report.consecutive_crits)
    if condition_type == "crit_finisher_count":
        return int(won and report.finisher_is_crit)
    if condition_type == "skill_finisher_count":
        return int(won and report.finisher_skill_id is not None)
    if condition_type == "elemental_finisher_kill_count":
        return int(won and ELEMENT_SKILLS.get(report.finisher_skill_id) == params.get("element"))
    return 0


# Стрики, сбрасываемые НЕвыполнением (а не просто +0) — единственный тип,
# завязанный на исход конкретного боя, не на отдых/поражение отдельно.
_RESET_ON_UNMET_BATTLE = {"win_streak_start_hp_below"}
# Стрики, сбрасываемые отдыхом и поражением (отдельные хуки ниже), не исходом боя.
_RESET_ON_REST = {"win_streak_no_rest"}
_RESET_ON_DEFEAT = {"win_streak_no_rest", "win_streak_start_hp_below"}


async def record_battle(db: AsyncSession, character: Character, report: BattleReport) -> list[str]:
    """Вызывать после КАЖДОГО PvE-боя игрока (и победы, и поражения)."""
    unlocked: list[str] = []
    for trial in await _active_trials(db, character):
        ct = trial.condition_type
        if ct == "reach_location_win":
            delta = 0
            if report.won and character.pos_x is not None and character.pos_y is not None:
                from game.world import location_types

                loc = location_types.location_type_at(character.pos_x, character.pos_y)
                delta = int(loc.id == trial.params.get("location_type"))
        else:
            delta = _battle_delta(ct, trial.params, report, character)

        if ct in _RESET_ON_UNMET_BATTLE and delta == 0:
            await _reset(db, character.id, trial)
            continue
        buff = await _apply_delta(db, character.id, trial, delta)
        if buff:
            unlocked.append(buff)
    return unlocked


async def record_defeat(db: AsyncSession, character: Character) -> None:
    """Поражение сбрасывает стрики «подряд» — не только бой без отдыха."""
    for trial in await _active_trials(db, character):
        if trial.condition_type in _RESET_ON_DEFEAT:
            await _reset(db, character.id, trial)


async def record_rest(db: AsyncSession, character: Character) -> None:
    for trial in await _active_trials(db, character):
        if trial.condition_type in _RESET_ON_REST:
            await _reset(db, character.id, trial)


async def record_combat_started(db: AsyncSession, character: Character) -> None:
    """Вход в бой обнуляет «пройти N клеток без единого боя»."""
    for trial in await _active_trials(db, character):
        if trial.condition_type == "walk_cells_no_combat":
            await _reset(db, character.id, trial)


async def record_cell_moved(db: AsyncSession, character: Character) -> list[str]:
    unlocked: list[str] = []
    for trial in await _active_trials(db, character):
        if trial.condition_type == "walk_cells_no_combat":
            buff = await _apply_delta(db, character.id, trial, 1)
            if buff:
                unlocked.append(buff)
    return unlocked


async def record_event_choice(db: AsyncSession, character: Character, event_id: str, choice: str) -> list[str]:
    unlocked: list[str] = []
    for trial in await _active_trials(db, character):
        if trial.condition_type != "event_choice_count":
            continue
        if trial.params.get("event") == event_id and trial.params.get("choice") == choice:
            buff = await _apply_delta(db, character.id, trial, 1)
            if buff:
                unlocked.append(buff)
    return unlocked


EVENT_CHOICE_CODES = {
    "Помочь": "help",
    "Помолиться": "pray",
    "Осквернить": "desecrate",
}


def buff_name(buff_id: str) -> str:
    from game.content_loader import load_content

    return load_content().buffs[buff_id].name


async def record_trophies(db: AsyncSession, character: Character, trophies: dict[str, int]) -> list[str]:
    if not trophies:
        return []
    unlocked: list[str] = []
    for trial in await _active_trials(db, character):
        if trial.condition_type != "collect_trophy_count":
            continue
        amount = trophies.get(trial.params.get("trophy_id"), 0)
        if amount <= 0:
            continue
        buff = await _apply_delta(db, character.id, trial, amount)
        if buff:
            unlocked.append(buff)
    return unlocked


async def unlocked_buff_ids(db: AsyncSession, character_id: int) -> set[str]:
    """Для гейта пресетов (services/preset_service.py, патч 12)."""
    rows = (
        await db.scalars(
            select(CharacterUnlockedBuff.buff_id).where(
                CharacterUnlockedBuff.character_id == character_id
            )
        )
    ).all()
    return set(rows)


@dataclass
class TrialState:
    trial: ClassTrialDef
    buff_name: str
    unlocked: bool
    progress: int
    target: int


async def get_trial_states(db: AsyncSession, character: Character) -> list[TrialState]:
    """Для чата Хранителя и мини-аппа (вкладка «Испытания»)."""
    if character.subclass is None:
        return []
    from game.content_loader import load_content

    catalog = load_content().buffs
    defs = trial_defs_for(character.subclass)
    rows = await _progress_rows(db, character.id, [d.id for d in defs])
    result = []
    for d in defs:
        row = rows.get(d.id)
        target = d.params.get("count", 1)
        result.append(
            TrialState(
                trial=d,
                buff_name=catalog[d.buff_id].name,
                unlocked=row.completed if row else False,
                progress=min(row.progress, target) if row else 0,
                target=target,
            )
        )
    return result
