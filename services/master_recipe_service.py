"""Мастерский рецепт алхимика (2026-10-23, решения владельца).

Игрокам ничего не подсказываем: кнопка рецепта на алхимическом столе
появляется сама, когда у алхимика нужного уровня в сумке уже всё есть.
Даёт эликсир (пьётся из сумки - постоянная прибавка к характеристикам),
перстень (все ремёсла вдвое) и титул. Один раз на персонажа.

Числа и id - game/economy/craft_gear_config.py (раздел «Мастерский рецепт»).
Находки (склянка, эликсир) хранятся строками CharacterCraftGear со
счётчиком: в инструменты они не выводятся (их нет в TOOLS).
"""

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import craft_gear_config as gc
from game.economy import fishing_config as fc
from models import Character, CharacterCraftGear, CharacterFish, CharacterFood, CharacterOre

VIAL_LINE = "🧪 Среди ящиков нашлась пыльная склянка с чужой печатью."
RING_TITLE = "Перстень Мастера"
RING_EFFECT = "Всё, что добывают и делают ремёсла, приходит вдвое"
DRAUGHT_TITLE = "Эликсир Мастера"


class MasterError(Exception):
    pass


def has_ring(character: Character) -> bool:
    return getattr(character, "ring_id", None) == gc.RING_ID


def ring_mult(character: Character) -> int:
    return gc.RING_MULT if has_ring(character) else 1


async def _counter(db: AsyncSession, character_id: int, key: str, lock: bool = False) -> CharacterCraftGear | None:
    query = select(CharacterCraftGear).where(
        CharacterCraftGear.character_id == character_id, CharacterCraftGear.tool_id == key,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def count_of(db: AsyncSession, character_id: int, key: str) -> int:
    row = await _counter(db, character_id, key)
    return row.count if row is not None else 0


async def _add(db: AsyncSession, character_id: int, key: str, amount: int = 1) -> None:
    row = await _counter(db, character_id, key, lock=True)
    if row is None:
        db.add(CharacterCraftGear(character_id=character_id, tool_id=key, tier=1, count=amount))
    else:
        row.count += amount
    await db.flush()


async def roll_vial(db: AsyncSession, character_id: int, rng: random.Random) -> bool:
    """Редкая находка в торговом рейсе."""
    if rng.random() >= gc.VIAL_CHANCE:
        return False
    await _add(db, character_id, gc.VIAL_ID)
    return True


async def _rows(db: AsyncSession, character_id: int):
    ore = (await db.scalars(select(CharacterOre).where(
        CharacterOre.character_id == character_id, CharacterOre.ore_id == gc.MASTER_ORE, CharacterOre.count > 0,
    ).with_for_update().execution_options(populate_existing=True))).all()
    fish = (await db.scalars(select(CharacterFish).where(
        CharacterFish.character_id == character_id, CharacterFish.fish_id == fc.NAMELESS_ID,
        CharacterFish.total_grams > 0,
    ).with_for_update().execution_options(populate_existing=True))).all()
    food = (await db.scalars(select(CharacterFood).where(
        CharacterFood.character_id == character_id, CharacterFood.dish_id == gc.MASTER_DISH, CharacterFood.count > 0,
    ).with_for_update().execution_options(populate_existing=True))).all()
    vial = await _counter(db, character_id, gc.VIAL_ID, lock=True)
    return ore, fish, food, vial


async def ready(db: AsyncSession, character: Character) -> bool:
    """Всё на месте - на столе появится кнопка рецепта."""
    if has_ring(character) or character.alchemy_level < gc.MASTER_ALCHEMY_LEVEL:
        return False
    if (character.star_dust or 0) < gc.MASTER_DUST:
        return False
    ore, fish, food, vial = await _rows(db, character.id)
    return bool(ore and fish and food and vial is not None and vial.count > 0)


async def brew(db: AsyncSession, character: Character) -> None:
    """Сварить: всё списывается разом, выдаётся эликсир, перстень и титул."""
    if not await ready(db, character):
        raise MasterError("Чего-то не хватает.")
    ore, fish, food, vial = await _rows(db, character.id)
    ore[0].count -= 1
    # Рыба лежит стаком по весу - уходит самый лёгкий стак целиком.
    min(fish, key=lambda r: r.total_grams).total_grams = 0
    food[0].count -= 1
    vial.count -= 1
    character.star_dust -= gc.MASTER_DUST
    from services import resource_log, title_service

    resource_log.add(db, character.id, "dust", None, -gc.MASTER_DUST)
    await _add(db, character.id, gc.DRAUGHT_ID)
    character.ring_id = gc.RING_ID
    await title_service.unlock(db, character, gc.TITLE_ID)
    await db.flush()


async def drink(db: AsyncSession, character: Character) -> None:
    """Выпить эликсир: прибавка ко всем характеристикам навсегда."""
    row = await _counter(db, character.id, gc.DRAUGHT_ID, lock=True)
    if row is None or row.count <= 0:
        raise MasterError("Эликсира нет.")
    if (character.perm_stat_pct or 0) >= gc.DRAUGHT_STAT_PCT:
        raise MasterError("Второй раз он ничего не даст.")
    row.count -= 1
    character.perm_stat_pct = gc.DRAUGHT_STAT_PCT
    await db.flush()
