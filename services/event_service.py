"""Исходы событий исследования (патч 9, блок 1).

Эффекты исхода комбинируемы (напр. trophy=True И damage — "Осквернить"
у Пепельного алтаря даёт трофей гарантированно + урон одновременно).
"""

import random
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import EventOutcome
from game.world import flavor
from game.world import world_config as wc
from models import Character, CharacterStats
from services import experience_service, trophy_service, vitals_service


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
) -> OutcomeResult:
    """Общее правило: события вне боя НЕ выдают боевых баффов — только опыт,
    трофеи, урон или ничего (или переход в бой при засаде)."""
    if outcome.combat:
        return OutcomeResult(outcome.text, is_combat=True)

    lines = [outcome.text] if outcome.text else []

    if outcome.trophy:
        drop = await trophy_service.grant_from_event(db, character, rng)
        drop_line = trophy_service.format_drop_line(drop)
        if drop_line:
            lines.append(drop_line)

    if outcome.xp:
        xp = round(experience_service.xp_per_mob(character.level) * wc.EVENT_XP_FRACTION)
        experience_service.add_experience(character, stats, xp)

    if outcome.damage_max_pct > 0:
        max_hp = vitals_service.max_hp(character, stats)
        current = vitals_service.current_hp(character, stats)
        pct = rng.uniform(outcome.damage_min_pct, outcome.damage_max_pct) / 100
        dmg = round(max_hp * pct)
        new_hp = max(1, current - dmg)  # событие вне боя не убивает
        vitals_service.set_hp(character, stats, new_hp)

    if outcome.song:
        lines.append(flavor.song_line(rng))

    if outcome.flavor:
        lines.append(flavor.song_or_remark(rng))

    return OutcomeResult("\n\n".join(line for line in lines if line))
