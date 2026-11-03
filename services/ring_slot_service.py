"""Слот кольца (2026-11-03, владелец: «слот кольца должен быть только 1»).

На пальце одно кольцо: Перстень Мастера (character.ring_id) или Перстень
Несгоревшего (character.resist_ring). Остальные лежат в сумке счётчиками
CharacterCraftGear (tool_id = id перстня) и не действуют. Надеть другое -
надетое уходит в сумку. Перстень Мастера не передаётся и не продаётся,
Несгоревшие - товар (transfer_service, рынок).
"""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import craft_gear_config as gc
from game.economy import resists
from models import Character

MASTER = "master"
UNBURNT = "unburnt"
#: Вид перстня -> счётчик в сумке.
BAG_KEY = {MASTER: gc.RING_ID, UNBURNT: resists.RING_ID}


class RingError(Exception):
    pass


def worn(character: Character) -> str | None:
    if getattr(character, "ring_id", None) == gc.RING_ID:
        return MASTER
    if character.resist_ring:
        return UNBURNT
    return None


def _set(character: Character, which: str | None) -> None:
    character.ring_id = gc.RING_ID if which == MASTER else None
    character.resist_ring = which == UNBURNT


async def _to_bag(db: AsyncSession, character: Character, which: str) -> None:
    from services import master_recipe_service

    await master_recipe_service._add(db, character.id, BAG_KEY[which])


async def _from_bag(db: AsyncSession, character: Character, which: str) -> bool:
    """Достать перстень из сумки. Условный UPDATE: два нажатия подряд не
    наденут один перстень дважды."""
    from models import CharacterCraftGear

    taken = await db.execute(
        update(CharacterCraftGear).where(
            CharacterCraftGear.character_id == character.id, CharacterCraftGear.tool_id == BAG_KEY[which],
            CharacterCraftGear.count >= 1,
        ).values(count=CharacterCraftGear.count - 1).execution_options(synchronize_session="fetch")
    )
    return bool(taken.rowcount)


async def give(db: AsyncSession, character: Character, which: str) -> str:
    """Новый перстень: палец свободен - сразу надет ("worn"), иначе в сумку ("bag")."""
    if worn(character) is None:
        _set(character, which)
        await db.flush()
        return "worn"
    await _to_bag(db, character, which)
    return "bag"


async def wear(db: AsyncSession, character: Character, which: str) -> None:
    """Надеть из сумки; надетый до этого уходит в сумку."""
    if which not in BAG_KEY:
        raise RingError("Такого перстня нет.")
    current = worn(character)
    if current == which:
        raise RingError("Перстень уже на пальце.")
    if not await _from_bag(db, character, which):
        raise RingError("Перстня в сумке нет.")
    if current is not None:
        await _to_bag(db, character, current)
    _set(character, which)
    await db.flush()


async def remove(db: AsyncSession, character: Character) -> None:
    current = worn(character)
    if current is None:
        raise RingError("Перстень не надет.")
    _set(character, None)
    await _to_bag(db, character, current)


def _info(which: str) -> dict:
    from services import master_recipe_service

    if which == MASTER:
        return {"id": MASTER, "name": master_recipe_service.RING_TITLE, "icon": "special:ring",
                "effect": master_recipe_service.RING_EFFECT, "flavor": None}
    lines = [resists.describe(kind, resists.RING_VALUE) for kind in resists.KINDS]
    return {"id": UNBURNT, "name": resists.RING_TITLE, "icon": "special:unburnt_ring",
            "effect": "; ".join(lines), "flavor": resists.RING_FLAVOR}


async def payload(db: AsyncSession, character: Character) -> dict | None:
    """Слот кольца в силуэте «Героя»: что на пальце и что в сумке (со
    счётом). None - перстней нет совсем, слот пустой."""
    from services import master_recipe_service

    current = worn(character)
    bag = []
    for which, key in BAG_KEY.items():
        count = await master_recipe_service.count_of(db, character.id, key)
        if count > 0:
            bag.append({**_info(which), "count": count, "tradable": which == UNBURNT})
    if current is None and not bag:
        return None
    return {"worn": _info(current) if current else None, "bag": bag}
