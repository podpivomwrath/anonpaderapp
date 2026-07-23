"""Координатная сетка: расстояние до Монолита, зоны сложности, города."""

from game.world import world_config as wc


def clamp(value: int) -> int:
    return max(wc.BOUNDS_MIN, min(wc.BOUNDS_MAX, value))


def chebyshev_distance(x: int, y: int) -> int:
    """Расстояние до Багряного Монолита (0;0)."""
    return max(abs(x), abs(y))


def zone_level_range(dist: int) -> tuple[int, int]:
    for lo, hi, levels in wc.ZONE_TABLE:
        if lo <= dist <= hi:
            return levels
    return wc.ZONE_TABLE[-1][2]  # недостижимо при dist в 0..50, но не оставляем без ответа


def city_region_at(x: int, y: int) -> str | None:
    """Регион города на этой клетке, если это клетка города (мирная зона)."""
    for region, coords in wc.CITY_COORDS.items():
        if coords == (x, y):
            return region
    return None


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def gate_exit_position(x: int, y: int) -> tuple[int, int]:
    """Клетка на выходе за ворота — один шаг к центру от города."""
    return clamp(x - _sign(x)), clamp(y - _sign(y))
