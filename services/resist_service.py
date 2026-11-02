"""Сопротивления персонажа (2026-11-02): руны, кованые вещи, Перстень
Несгоревшего - в ключи resist_crit / accuracy / resist_dot для боя и сводки.
Числа и правила - game/economy/resists.py. Стойкость к критам от Выносливости
считает сам бой (stat_model.crit_resist), здесь её нет."""

import random

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
    return mods


def ring_payload(character: Character) -> dict | None:
    if not character.resist_ring:
        return None
    lines = [resists.describe(kind, resists.RING_VALUE) for kind in resists.KINDS]
    return {"name": resists.RING_TITLE, "effect": "; ".join(lines), "flavor": resists.RING_FLAVOR}


async def maybe_drop_ring(db: AsyncSession, character: Character, rng: random.Random) -> bool:
    """Шанс перстня за победу над мобом клетки. Уже есть - второго не бывает.
    Без объявлений (владелец): игрок узнаёт по строке в добыче."""
    if character.resist_ring or rng.random() >= resists.RING_DROP_CHANCE:
        return False
    character.resist_ring = True
    from services import resource_log

    resource_log.add(db, character.id, "ring", resists.RING_ID, 1)
    await db.flush()
    return True
