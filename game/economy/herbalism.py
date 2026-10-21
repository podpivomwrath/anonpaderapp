"""Травничество: чистая логика без БД (2026-10-21). Числа - herbal_config."""

import random

from game.content_loader import HerbDef, load_herb_defs
from game.economy import herbal_config as hc
from game.world import grid
from game.world import world_config as wc

_defs: dict[str, HerbDef] | None = None


def _herbs() -> dict[str, HerbDef]:
    global _defs
    if _defs is None:
        _defs = {h.id: h for h in load_herb_defs()}
    return _defs


def herb_def(herb_id: str) -> HerbDef | None:
    return _herbs().get(herb_id)


def herb_defs_ordered() -> list[HerbDef]:
    return list(_herbs().values())


def required_level(herb: HerbDef) -> int:
    return hc.TIER_LEVEL[herb.tier]


def can_see(level: int, herb: HerbDef) -> bool:
    return level >= required_level(herb)


def roll_herb(rng: random.Random, x: int, y: int) -> HerbDef:
    """Тир - от кольца клетки с перекосом, вид внутри тира - поровну."""
    ring = grid.ring_tier(x, y)
    tiers = sorted(hc.TIER_LEVEL)
    weights = [hc.RING_TIER_WEIGHT if t == ring else 1 for t in tiers]
    tier = rng.choices(tiers, weights=weights)[0]
    return rng.choice([h for h in herb_defs_ordered() if h.tier == tier])


def roll_cell(rng: random.Random, taken: set[tuple[int, int]], tries: int = 30) -> tuple[int, int] | None:
    """Случайная клетка мира: не город, не занятая травой, не из taken."""
    for _ in range(tries):
        x = rng.randint(wc.BOUNDS_MIN, wc.BOUNDS_MAX)
        y = rng.randint(wc.BOUNDS_MIN, wc.BOUNDS_MAX)
        if grid.in_bounds(x, y) and grid.city_region_at(x, y) is None and (x, y) not in taken:
            return x, y
    return None


def xp_to_next(level: int) -> int:
    """0 - потолок, дальше расти некуда."""
    if level >= hc.MAX_LEVEL:
        return 0
    return hc.XP_BASE + hc.XP_PER_LEVEL * level


def double_chance(level: int) -> float:
    return hc.DOUBLE_PER_10_LEVELS * (level // 10)


def pick_xp(herb: HerbDef) -> int:
    return hc.PICK_XP[herb.tier]


def unlocked_between(old_level: int, new_level: int) -> list[HerbDef]:
    """Травы, которые стали видны на этом подъёме уровня."""
    return [h for h in herb_defs_ordered() if old_level < required_level(h) <= new_level]
