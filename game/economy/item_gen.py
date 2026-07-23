"""Генерация базовой экипировки (патч 11, блок 2) — чистая логика без БД.

Дроп предмета — таблица, НЕЗАВИСИМАЯ от трофеев (патч 9): сначала шанс "выпал
ли предмет вообще" (ITEM_DROP_CHANCE), затем при удаче — редкость, слот —
равновероятно.
"""

import math
import random
from dataclasses import dataclass

from game.content_loader import ItemBaseDef, ItemRarityDef
from game.economy import item_config as ic


def item_power(ilvl: int, rarity_mult: float) -> int:
    """floor((floor(ilvl*0.25) + 2) * rarity_mult) — сумма очков статов предмета."""
    return math.floor((math.floor(ilvl * ic.ILVL_DIVISOR) + ic.ILVL_BASE) * rarity_mult)


def distribute_stats(power: int, slot: str, primary_stat: str) -> dict[str, int]:
    """Делит power между статами слота; остаток округления уходит первому стату."""
    splits = ic.SLOT_STAT_SPLITS[slot]
    resolved = [(primary_stat if key == "primary" else key, frac) for key, frac in splits]

    if len(resolved) == 1:
        return {resolved[0][0]: power}

    (first_key, first_frac), (second_key, _) = resolved
    first_amount = math.floor(power * first_frac + 0.5)  # half-up, в пользу первого
    second_amount = power - first_amount

    result: dict[str, int] = {}
    result[first_key] = result.get(first_key, 0) + first_amount
    result[second_key] = result.get(second_key, 0) + second_amount
    return result


def roll_rarity(rng: random.Random) -> str | None:
    """None — предмет не выпал вообще (1 - ITEM_DROP_CHANCE)."""
    if rng.random() >= ic.ITEM_DROP_CHANCE:
        return None
    roll = rng.random()
    cumulative = 0.0
    rarities = list(ic.ITEM_RARITY_CHANCES.items())
    for rarity_id, chance in rarities:
        cumulative += chance
        if roll < cumulative:
            return rarity_id
    return rarities[-1][0]  # защита от погрешности суммы шансов с плавающей точкой


def roll_slot(rng: random.Random) -> str:
    return rng.choice(ic.SLOTS)


def build_name(base: ItemBaseDef, rarity: ItemRarityDef) -> str:
    """Легендарная — суффикс ПОСЛЕ базы, родительный падеж ("Кираса Монолита").
    Остальные — суффикс-прилагательное ПЕРЕД базой ("Кровавый клинок")."""
    if rarity.suffix.invariant:
        return f"{base.name} {rarity.suffix.invariant}"
    suffix = getattr(rarity.suffix, base.gender)
    suffix_cap = suffix[0].upper() + suffix[1:]
    return f"{suffix_cap} {base.name.lower()}"


@dataclass
class GeneratedItem:
    name: str
    slot: str
    rarity: str
    ilvl: int
    power: int
    base_stats: dict[str, int]


def generate_item(
    rng: random.Random,
    ilvl: int,
    slot: str,
    rarity_id: str,
    primary_stat: str,
    bases: dict[str, list[ItemBaseDef]],
    rarities: dict[str, ItemRarityDef],
) -> GeneratedItem:
    rarity = rarities[rarity_id]
    base = rng.choice(bases[slot])
    power = item_power(ilvl, rarity.mult)
    stats = distribute_stats(power, slot, primary_stat)
    return GeneratedItem(
        name=build_name(base, rarity),
        slot=slot,
        rarity=rarity_id,
        ilvl=ilvl,
        power=power,
        base_stats=stats,
    )
