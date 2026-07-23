"""Дроп трофеев (патч 9, блок 2): независимые броски по таблице шансов.

Чистая логика без БД — так же, как game/combat/formulas.py. Запись начислений
в БД — services/trophy_service.py.
"""

import random

from game.economy import loot_config as lc


def rolls_for_dist(dist: int) -> int:
    """Число независимых бросков по расстоянию Чебышёва до Монолита."""
    for lo, hi, rolls in lc.ROLLS_BY_DIST:
        if lo <= dist <= hi:
            return rolls
    return lc.ROLLS_BY_DIST[-1][2]  # недостижимо при dist в 0..50


def roll_once(rng: random.Random) -> str | None:
    """Один бросок; None — ничего не выпало (~31.15% при базовых шансах)."""
    roll = rng.random()
    cumulative = 0.0
    for trophy_id, chance in lc.TROPHY_ROLL_CHANCES.items():
        cumulative += chance
        if roll < cumulative:
            return trophy_id
    return None


def roll_drop(rng: random.Random, rolls: int) -> dict[str, int]:
    """`rolls` независимых бросков подряд; возвращает {trophy_id: count}
    только для выпавших градаций (за один бой может выпасть несколько разных)."""
    result: dict[str, int] = {}
    for _ in range(rolls):
        trophy_id = roll_once(rng)
        if trophy_id is not None:
            result[trophy_id] = result.get(trophy_id, 0) + 1
    return result
