"""Горстка пепла — находка после исследования (патч 25, п.4): немного опыта +
1 бросок трофеев + очень редко предмет экипировки. Само появление кнопки
(шанс ~20%) и её жизненный цикл (одноразовая/сгорает) — bot/ash_handful_state.py,
здесь только начисление награды при сборе."""

import random
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import ash_config as ac
from game.world import grid
from models import Character, CharacterStats, Item
from services import experience_service, item_service, trophy_service


def roll_appears(rng: random.Random) -> bool:
    return rng.random() < ac.ASH_HANDFUL_CHANCE


@dataclass
class AshCollectResult:
    xp: int
    trophies: dict[str, int]
    item: Item | None
    levels_gained: int
    new_level: int


async def collect(
    db: AsyncSession, character: Character, stats: CharacterStats, rng: random.Random,
) -> AshCollectResult:
    zone_level = grid.mob_level_at(character.pos_x, character.pos_y, character.level)
    xp = experience_service.event_xp(zone_level, character.level, ac.EVENT_XP_ASH)
    levelup = experience_service.add_experience(character, stats, xp)
    trophies = await trophy_service.grant_from_event(db, character, rng)  # 1 бросок
    item = None
    if rng.random() < ac.ASH_ITEM_CHANCE:
        item = await item_service.grant_random_item(db, character, character.level, rng)
    return AshCollectResult(
        xp=xp, trophies=trophies, item=item,
        levels_gained=levelup.levels_gained, new_level=levelup.new_level,
    )
