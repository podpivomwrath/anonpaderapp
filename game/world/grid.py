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


def mob_level_at(x: int, y: int, player_level: int) -> int:
    """Уровень, который имел бы обычный моб на этой клетке —
    clamp(player_level, zone_min, zone_max), та же формула, что и у обычных
    мобов (game/world/encounters.py::mob_level_for_player), только по
    произвольным координатам, а не по конкретному мобу бестиария.

    Патч 36: квестовые (named) враги и опыт с небоевых событий (горстка
    пепла, события исследования) были жёстко привязаны к уровню ИГРОКА без
    этого клампа — далёкий забег на дальнее кольцо или возврат прокачанным
    персонажем в старую локацию давал противника/награду не по месту, а по
    текущему уровню персонажа. Эта функция — общая точка привязки к клетке."""
    zone_min, zone_max = zone_level_range(chebyshev_distance(x, y))
    return max(zone_min, min(player_level, zone_max))


def city_region_at(x: int, y: int) -> str | None:
    """Регион города на этой клетке, если это клетка города (мирная зона)."""
    for region, coords in wc.CITY_COORDS.items():
        if coords == (x, y):
            return region
    return None


def in_bounds(x: int, y: int) -> bool:
    """Клетка (x;y) — в пределах сетки -50..50 по обеим осям (патч 17)."""
    return wc.BOUNDS_MIN <= x <= wc.BOUNDS_MAX and wc.BOUNDS_MIN <= y <= wc.BOUNDS_MAX
