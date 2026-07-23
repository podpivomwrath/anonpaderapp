"""Исходы событий исследования (патч 9 блок 1, патч 10 блок 3).

Эффекты исхода комбинируемы (напр. trophy=True И damage — "Осквернить"
у Пепельного алтаря даёт трофей гарантированно + урон одновременно).
Пустых исходов ("ничего не произошло") с патча 10 не бывает.
"""

import random
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import EventOutcome
from game.world import world_config as wc
from models import Character, CharacterStats
from services import experience_service, item_service, trial_service, trophy_service, vitals_service


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

    if character.subclass is not None and event_id is not None and choice_code is not None:
        await trial_service.record_event_choice(db, character, event_id, choice_code)

    if outcome.trophy:
        drop = await trophy_service.grant_from_event(db, character, rng)
        drop_line = trophy_service.format_drop_line(drop)
        if drop_line:
            lines.append(drop_line)
        if character.subclass is not None:
            await trial_service.record_trophies(db, character, drop)

    if outcome.xp or outcome.xp_big:
        fraction = wc.EVENT_XP_FRACTION_BIG if outcome.xp_big else wc.EVENT_XP_FRACTION
        xp = round(experience_service.xp_per_mob(character.level) * fraction)
        experience_service.add_experience(character, stats, xp)

    if outcome.damage_max_pct > 0:
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        current = vitals_service.current_hp(character, stats, vit_bonus)
        pct = rng.uniform(outcome.damage_min_pct, outcome.damage_max_pct) / 100
        dmg = round(max_hp * pct)
        new_hp = max(1, current - dmg)  # событие вне боя не убивает
        vitals_service.set_hp(character, stats, new_hp, vit_bonus)

    return OutcomeResult("\n\n".join(line for line in lines if line))
