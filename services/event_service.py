"""Исходы событий исследования (патч 9 блок 1, патч 10 блок 3).

Эффекты исхода комбинируемы (напр. trophy=True И damage — "Осквернить"
у Пепельного алтаря даёт трофей гарантированно + урон одновременно).
Пустых исходов ("ничего не произошло") с патча 10 не бывает.
"""

import random
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import display
from bot import raid_key_texts
from game.content_loader import EventOutcome
from game.world import grid
from game.world import world_config as wc
from models import Character, CharacterStats
from services import (
    daily_service,
    experience_service,
    item_service,
    raid_key_service,
    trial_service,
    trophy_service,
    vitals_service,
)


def pick_outcome(rng: random.Random, outcomes: list[EventOutcome]) -> EventOutcome:
    """Взвешенный выбор исхода из выбора игрока."""
    total = sum(o.weight for o in outcomes)
    roll = rng.uniform(0, total)
    cumulative = 0.0
    for outcome in outcomes:
        cumulative += outcome.weight
        if roll < cumulative:
            return outcome
    return outcomes[-1]


@dataclass
class OutcomeResult:
    text: str
    is_combat: bool = False
    levels_gained: int = 0
    new_level: int = 1
    daily_completed: list = field(default_factory=list)  # daily_service.DailyCompletion
    daily_streak_notice: str | None = None
    raid_key_dropped: bool = False  # патч 45, ч.4 — Ключ Монолита


async def apply_outcome(
    db: AsyncSession,
    character: Character,
    stats: CharacterStats,
    outcome: EventOutcome,
    rng: random.Random,
    event_id: str | None = None,
    choice_code: str | None = None,
) -> OutcomeResult:
    """Общее правило (патч 10, блок 3): события вне боя НЕ выдают боевых баффов
    и никогда не дают пустой исход — только опыт, трофеи, урон, бой (или их
    комбинация). event_id/choice_code (патч 12) — прогресс классовых испытаний
    типа event_choice_count; передаются вызывающим кодом (см. bot/handlers/world.py)."""
    if outcome.combat:
        return OutcomeResult(outcome.text, is_combat=True)

    lines = [outcome.text] if outcome.text else []
    daily_completed = []
    daily_streak_notice = None

    if character.subclass is not None and event_id is not None and choice_code is not None:
        # trial_service.EVENT_CHOICE_CODES — узкий словарь ТОЛЬКО для конкретных
        # испытаний подклассов ("Помочь"/"Помолиться"/"Осквернить"); намеренно
        # не покрывает все варианты выбора всех событий.
        await trial_service.record_event_choice(db, character, event_id, choice_code)
    if event_id is not None:
        # Патч 45, ч.3 (репорт #19): ежедневка «Любопытный» засчитывается по
        # самому ФАКТУ выбора в любом событии — раньше здесь ошибочно стояло
        # то же условие choice_code is not None, что и для испытаний выше,
        # из-за чего варианты вне узкого словаря trial_service (Пройти мимо,
        # Вскрыть, Оставить, Коснуться, Отколоть кусок и т.д.) не засчитывались.
        progress = await daily_service.record_event_choice(db, character)
        daily_completed += progress.completed
        daily_streak_notice = daily_streak_notice or progress.streak_notice

    # Патч 45, ч.4: Ключ Монолита падает независимым броском с ЛЮБОГО
    # источника лута, не только там, где outcome.trophy — проверяем всегда.
    raid_key_dropped = await raid_key_service.maybe_grant(db, character, rng)
    if raid_key_dropped:
        lines.append(raid_key_texts.raid_key_drop_line())

    reward_added = False

    if outcome.trophy:
        drop = await trophy_service.grant_from_event(db, character, rng)
        # Патч 32, ч.2: формулировка получения — по конкретному событию
        # (шкатулка/осколок/путник/алтарь), не общий боевой шаблон "с твари".
        drop_line = trophy_service.format_drop_line(drop, source=event_id or "mob")
        if drop_line:
            lines.append(drop_line)
            reward_added = True
        if character.subclass is not None:
            await trial_service.record_trophies(db, character, drop)
        progress = await daily_service.record_trophies(db, character, drop)
        daily_completed += progress.completed
        daily_streak_notice = daily_streak_notice or progress.streak_notice

    levels_gained = 0
    new_level = character.level
    if outcome.xp or outcome.xp_big:
        share = wc.EVENT_XP_RISKY if outcome.xp_big else wc.EVENT_XP_SAFE
        zone_level = grid.mob_level_at(character.pos_x, character.pos_y, character.level)
        xp = experience_service.event_xp(zone_level, character.level, share)
        levelup = experience_service.add_experience(character, stats, xp)
        levels_gained, new_level = levelup.levels_gained, levelup.new_level
        lines.append(display.xp_delta_line(xp))
        reward_added = True

    if outcome.damage_max_pct > 0:
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        current = vitals_service.current_hp(character, stats, vit_bonus)
        pct = rng.uniform(outcome.damage_min_pct, outcome.damage_max_pct) / 100
        dmg = round(max_hp * pct)
        new_hp = max(1, current - dmg)  # событие вне боя не убивает
        vitals_service.set_hp(character, stats, new_hp, vit_bonus)
        lines.append(display.hp_delta_line(current, new_hp, max_hp))
        reward_added = True

    if not reward_added:
        # Патч 38: защитная сетка — исход не сформировал ни одного видимого
        # результата (контентная ошибка: ни trophy/xp/xp_big/damage не
        # объявлены, либо один из них не смог начислиться) — игрок не должен
        # уходить с пустыми руками из-за бага, но это ДОЛЖНО попасть в лог.
        logger.error(
            "Событие без результата — выдана аварийная минимальная награда: "
            "event_id={} choice_code={} outcome_weight={} outcome_text={!r}",
            event_id, choice_code, outcome.weight, outcome.text,
        )
        zone_level = grid.mob_level_at(character.pos_x, character.pos_y, character.level)
        xp = experience_service.event_xp(zone_level, character.level, wc.EVENT_XP_SAFE)
        levelup = experience_service.add_experience(character, stats, xp)
        levels_gained, new_level = levelup.levels_gained, levelup.new_level
        lines.append(display.xp_delta_line(xp))

    return OutcomeResult(
        "\n\n".join(line for line in lines if line), levels_gained=levels_gained, new_level=new_level,
        daily_completed=daily_completed, daily_streak_notice=daily_streak_notice,
        raid_key_dropped=raid_key_dropped,
    )
