"""Сопротивления персонажа (2026-11-02): руны, кованые вещи, Перстень
Несгоревшего - в ключи resist_crit / accuracy / resist_dot для боя и сводки.
Числа и правила - game/economy/resists.py. Стойкость к крит-урону от Выносливости
считает сам бой (stat_model.crit_resist), здесь её нет."""

import random

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import resists
from models import Character, Item

#: Руна героя -> вид сопротивления. Значение уже с поправкой PvP.
RUNE_KINDS = {"rune:tempered": resists.CRIT, "rune:true_eye": resists.DODGE, "rune:bitter_blood": resists.DOT}


def item_line(item: Item) -> str | None:
    """Строка сопротивления кованой вещи или None."""
    if item.craft_resist not in resists.KINDS:
        return None
    return resists.describe(item.craft_resist, resists.item_value(item.craft_efficiency))


def item_chip(item: Item) -> dict | None:
    """Плашка сопротивления для мини-аппа: {"emoji", "pct"} или None."""
    if item.craft_resist not in resists.KINDS:
        return None
    return {"emoji": resists.EMOJI[item.craft_resist],
            "pct": round(resists.item_value(item.craft_efficiency) * 100, 1)}


def roll_for(item: Item, rng: random.Random) -> None:
    """Ковка и перековка: новое случайное сопротивление."""
    item.craft_resist = resists.roll(rng)


async def modifiers(db: AsyncSession, character: Character, runes: dict[str, float]) -> dict[str, float]:
    from services import item_service

    mods: dict[str, float] = {}
    for key, kind in RUNE_KINDS.items():
        resists.add(mods, kind, runes.get(key, 0.0))
    if character.id is not None:
        for item in (await item_service.get_equipped(db, character.id)).values():
            if item is not None and item.craft_resist in resists.KINDS:
                resists.add(mods, item.craft_resist, resists.item_value(item.craft_efficiency))
    if character.resist_ring:
        for kind in resists.KINDS:
            resists.add(mods, kind, resists.RING_VALUE)
    # Мягкий потолок на сумму вида: стопки вещей не обнуляют криты и яды.
    return {key: resists.capped(value) for key, value in mods.items()}


class RingError(Exception):
    pass


async def spare_rings(db: AsyncSession, character_id: int) -> int:
    """Ненадетые перстни в сумке (2026-11-02): их передают и продают.
    Надетый - character.resist_ring, в сумке его нет."""
    from services import master_recipe_service

    return await master_recipe_service.count_of(db, character_id, resists.RING_ID)


async def ring_payload(db: AsyncSession, character: Character) -> dict | None:
    """Слот перстня в силуэте: worn - надет ли, spare - сколько в сумке.
    None - перстней нет совсем, слота не видно."""
    spare = await spare_rings(db, character.id)
    if not character.resist_ring and spare <= 0:
        return None
    lines = [resists.describe(kind, resists.RING_VALUE) for kind in resists.KINDS]
    return {"name": resists.RING_TITLE, "effect": "; ".join(lines), "flavor": resists.RING_FLAVOR,
            "worn": bool(character.resist_ring), "spare": spare}


async def wear(db: AsyncSession, character: Character) -> None:
    """Надеть перстень из сумки. Списание условным UPDATE: два нажатия
    подряд не наденут один перстень дважды."""
    from models import CharacterCraftGear

    if character.resist_ring:
        raise RingError("Перстень уже на пальце.")
    taken = await db.execute(
        update(CharacterCraftGear).where(
            CharacterCraftGear.character_id == character.id, CharacterCraftGear.tool_id == resists.RING_ID,
            CharacterCraftGear.count >= 1,
        ).values(count=CharacterCraftGear.count - 1).execution_options(synchronize_session="fetch")
    )
    if not taken.rowcount:
        raise RingError("Перстня в сумке нет.")
    character.resist_ring = True
    await db.flush()


async def remove(db: AsyncSession, character: Character) -> None:
    """Снять перстень в сумку - тогда его можно передать или продать."""
    from services import master_recipe_service

    if not character.resist_ring:
        raise RingError("Перстень не надет.")
    character.resist_ring = False
    await master_recipe_service._add(db, character.id, resists.RING_ID)


async def add_ring(db: AsyncSession, character: Character) -> str:
    """Новый перстень: слот пуст - сразу на палец ("worn"), занят - в
    сумку ("bag"), лишний - товар на продажу."""
    from services import master_recipe_service

    if not character.resist_ring:
        character.resist_ring = True
        await db.flush()
        return "worn"
    await master_recipe_service._add(db, character.id, resists.RING_ID)
    return "bag"


async def maybe_drop_ring(db: AsyncSession, character: Character, rng: random.Random) -> str | None:
    """Шанс перстня за победу над мобом (2026-11-02: второй тоже падает).
    Без объявлений (владелец): игрок узнаёт по строке в добыче."""
    if rng.random() >= resists.RING_DROP_CHANCE:
        return None
    from services import resource_log

    resource_log.add(db, character.id, "ring", resists.RING_ID, 1)
    return await add_ring(db, character)
