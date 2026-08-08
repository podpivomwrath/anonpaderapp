"""Исходы событий исследования (патч 9 блок 1, патч 10 блок 3).

Эффекты исхода комбинируемы (напр. trophy=True И damage — "Осквернить"
у Пепельного алтаря даёт трофей гарантированно + урон одновременно).
Пустых исходов ("ничего не произошло") с патча 10 не бывает.
"""

import random
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import display
from game.content_loader import EventOutcome
from game.world import world_config as wc
from models import Character, CharacterStats
from services import daily_service, experience_service, item_service, trial_service, trophy_service, vitals_service


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
        await trial_service.record_event_choice(db, character, event_id, choice_code)
    if event_id is not None and choice_code is not None:
        progress = await daily_service.record_event_choice(db, character)
        daily_completed += progress.completed
        daily_streak_notice = daily_streak_notice or progress.streak_notice

    if outcome.trophy:
        drop = await trophy_service.grant_from_event(db, character, rng)
        # Патч 32, ч.2: формулировка получения — по конкретному событию
        # (шкатулка/осколок/путник/алтарь), не общий боевой шаблон "с твари".
        drop_line = trophy_service.format_drop_line(drop, source=event_id or "mob")
        if drop_line:
            lines.append(drop_line)
        if character.subclass is not None:
            await trial_service.record_trophies(db, character, drop)
        progress = await daily_service.record_trophies(db, character, drop)
        daily_completed += progress.completed
        daily_streak_notice = daily_streak_notice or progress.streak_notice

    levels_gained = 0
    new_level = character.level
    if outcome.xp or outcome.xp_big:
        fraction = wc.EVENT_XP_FRACTION_BIG if outcome.xp_big else wc.EVENT_XP_FRACTION
        xp = round(experience_service.xp_per_mob(character.level) * fraction)
        levelup = experience_service.add_experience(character, stats, xp)
        levels_gained, new_level = levelup.levels_gained, levelup.new_level
        lines.append(display.xp_delta_line(xp))

    if outcome.damage_max_pct > 0:
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        current = vitals_service.current_hp(character, stats, vit_bonus)
        pct = rng.uniform(outcome.damage_min_pct, outcome.damage_max_pct) / 100
        dmg = round(max_hp * pct)
        new_hp = max(1, current - dmg)  # событие вне боя не убивает
        vitals_service.set_hp(character, stats, new_hp, vit_bonus)
        lines.append(display.hp_delta_line(current, new_hp, max_hp))

    return OutcomeResult(
        "\n\n".join(line for line in lines if line), levels_gained=levels_gained, new_level=new_level,
        daily_completed=daily_completed, daily_streak_notice=daily_streak_notice,
    )
