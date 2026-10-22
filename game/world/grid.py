"""Координатная сетка: расстояние до Монолита, зоны сложности, города.

Патч 108: мир круглый. Сетка клеток осталась квадратной (ходы по 8
направлениям, путь маунта в клетках), но кольца и край мира считаются по
округлённому евклидову расстоянию до Монолита - настоящие круги.
"""

import math

from game.world import world_config as wc


def clamp(value: int) -> int:
    return max(wc.BOUNDS_MIN, min(wc.BOUNDS_MAX, value))


def monolith_distance(x: int, y: int) -> int:
    """Расстояние до Багряного Монолита (0;0) - округлённое евклидово."""
    return round(math.hypot(x, y))


def ring_tier(x: int, y: int) -> int:
    """Кольцо клетки: 1 - внешнее, 5 - центр."""
    return wc.ring_tier_for_dist(monolith_distance(x, y))


def cells_between(x1: int, y1: int, x2: int, y2: int) -> int:
    """Длина пути в клетках при ходах по 8 направлениям."""
    return max(abs(x2 - x1), abs(y2 - y1))


def line_path(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int]]:
    """Клетки пути от (x1;y1) к (x2;y2) по 8 направлениям, без стартовой и с
    конечной. Длина ровно cells_between, каждый шаг - в соседнюю клетку.
    Прямая между двумя точками круга целиком лежит в круге, поэтому край
    мира путь не пересекает."""
    n = cells_between(x1, y1, x2, y2)
    return [
        (x1 + round((x2 - x1) * i / n), y1 + round((y2 - y1) * i / n))
        for i in range(1, n + 1)
    ]


#: Штраф безопасного пути за шаг на клетку кольца опаснее цели - за каждое
#: кольцо сверх. Такой, что любой обход дешевле, чем зайти внутрь.
SAFE_PATH_PENALTY = 1000


def safe_path(x1: int, y1: int, x2: int, y2: int) -> list[tuple[int, int]]:
    """Безопасный путь (2026-10-13): клетки без стартовой и с конечной, по 8
    направлениям, не заходя в кольца опаснее кольца цели (ближе к центру).
    Если старт сам в таком кольце - выходит из него кратчайшим путём. Обход
    дольше прямой; путь всегда находится - внутри мира всё связно."""
    import heapq

    limit = ring_tier(x2, y2)
    start, goal = (x1, y1), (x2, y2)
    if start == goal:
        return []
    best = {start: 0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    queue = [(0, 0, 0, start)]
    order = 0
    while queue:
        cost, _, _, cell = heapq.heappop(queue)
        if cell == goal:
            break
        if cost > best.get(cell, cost):
            continue
        cx, cy = cell
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not dx and not dy:
                    continue
                nxt = (cx + dx, cy + dy)
                if not in_bounds(*nxt):
                    continue
                step = 1 + SAFE_PATH_PENALTY * max(0, ring_tier(*nxt) - limit)
                new = cost + step
                if new < best.get(nxt, new + 1):
                    best[nxt] = new
                    came[nxt] = cell
                    order += 1
                    # Тай-брейк - ближе к цели: путь ровнее, без петель.
                    heapq.heappush(queue, (new, cells_between(*nxt, *goal), order, nxt))
    path = []
    cell = goal
    while cell != start:
        path.append(cell)
        cell = came[cell]
    return path[::-1]


def zone_level_range(dist: int) -> tuple[int, int]:
    return wc.ZONE_TABLE[wc.ring_tier_for_dist(dist) - 1][2]


def mob_level_at(x: int, y: int, player_level: int) -> int:
    """Уровень, который имел бы обычный моб на этой клетке —
    wc.ring_mob_level (середина кольца, если игрок ниже него), та же формула, что и у обычных
    мобов (game/world/encounters.py::mob_level_for_player), только по
    произвольным координатам, а не по конкретному мобу бестиария.

    Патч 36: квестовые (named) враги и опыт с небоевых событий (горстка
    пепла, события исследования) были жёстко привязаны к уровню ИГРОКА без
    этого клампа — далёкий забег на дальнее кольцо или возврат прокачанным
    персонажем в старую локацию давал противника/награду не по месту, а по
    текущему уровню персонажа. Эта функция — общая точка привязки к клетке."""
    # 2026-10-15: уровень - клетки, игрок больше не влияет (player_level
    # оставлен в сигнатуре для вызывающих).
    return wc.cell_base_level(monolith_distance(x, y))


def city_region_at(x: int, y: int) -> str | None:
    """Регион города на этой клетке, если это клетка города (мирная зона)."""
    for region, coords in wc.CITY_COORDS.items():
        if coords == (x, y):
            return region
    return None


def at_city_gates(x: int, y: int) -> bool:
    """Клетка у города - в пределах CITY_SAFE_RADIUS во все стороны (с
    2026-10-15 - 2 клетки). Под защитой от PvP, как сам город: иначе
    выходящего из ворот ждали прямо за стеной. Мобы тут есть."""
    return any(
        0 < max(abs(x - cx), abs(y - cy)) <= wc.CITY_SAFE_RADIUS for cx, cy in wc.CITY_COORDS.values()
    )


def is_monolith(x: int, y: int) -> bool:
    return (x, y) == (0, 0)


def pvp_forbidden(x: int, y: int) -> bool:
    """Город, клетка у его ворот или Монолит (0;0, с 2026-10-22): игроки
    здесь не нападают друг на друга."""
    return city_region_at(x, y) is not None or at_city_gates(x, y) or is_monolith(x, y)


def in_bounds(x: int, y: int) -> bool:
    """Клетка (x;y) - внутри круга мира (патч 108)."""
    return monolith_distance(x, y) <= wc.WORLD_RADIUS


def all_cells() -> list[tuple[int, int]]:
    return [
        (x, y)
        for x in range(wc.BOUNDS_MIN, wc.BOUNDS_MAX + 1)
        for y in range(wc.BOUNDS_MIN, wc.BOUNDS_MAX + 1)
        if in_bounds(x, y)
    ]
