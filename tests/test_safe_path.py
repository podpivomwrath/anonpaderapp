"""Безопасный путь верхом (2026-10-13): не заходит в кольца опаснее цели.
С 2026-11-08 верхом - не заходит на клетки с мобами сильнее, чем у цели."""

import time

from game.world import grid
from game.world import world_config as wc


def _check(path, x1, y1, x2, y2):
    assert path[-1] == (x2, y2)
    prev = (x1, y1)
    for cell in path:
        assert grid.cells_between(*prev, *cell) == 1 and grid.in_bounds(*cell)
        prev = cell


def _lvl(cell) -> int:
    return wc.cell_base_level(grid.monolith_distance(*cell))


def test_goes_around_inner_rings() -> None:
    # с запада на восток через центр: прямая режет IV кольцо, безопасный - нет
    x1, y1, x2, y2 = -20, 0, 20, 0
    straight = grid.line_path(x1, y1, x2, y2)
    safe = grid.safe_path(x1, y1, x2, y2, by_level=False)
    _check(safe, x1, y1, x2, y2)
    limit = grid.ring_tier(x2, y2)
    assert max(grid.ring_tier(*c) for c in straight) > limit
    assert max(grid.ring_tier(*c) for c in safe) <= limit
    assert len(safe) > len(straight)


def test_leaves_inner_ring_when_starting_inside() -> None:
    safe = grid.safe_path(0, 3, 0, wc.ring_bounds(1)[0])
    _check(safe, 0, 3, 0, wc.ring_bounds(1)[0])


def test_same_ring_short_trip_is_straight_length() -> None:
    assert len(grid.safe_path(20, 0, 22, 2)) == grid.cells_between(20, 0, 22, 2)


def test_safe_straight_line_stays_straight() -> None:
    """Прямая и так не опаснее цели - безопасный путь её не ломает (жалоба
    2026-11-08: вдоль края путь нырял к центру той же длиной)."""
    for args in ((0, 30, 10, 26), (5, 25, -12, 18)):
        straight = grid.line_path(*args)
        if all(_lvl(c) <= _lvl(args[2:]) for c in straight):
            assert grid.safe_path(*args) == straight
    assert grid.safe_path(0, 30, 10, 26) == grid.line_path(0, 30, 10, 26)


def test_no_cell_stronger_than_target() -> None:
    """Уровень мобов растёт к центру плавно: в кольце II нельзя по пути к
    клетке 16-го уровня зайти на клетку 27-го."""
    for x1, y1, x2, y2 in ((24, 0, 22, 8), (3, 20, 16, 12), (-20, 0, 20, 0), (0, 30, 25, 10)):
        safe = grid.safe_path(x1, y1, x2, y2)
        _check(safe, x1, y1, x2, y2)
        assert max(_lvl(c) for c in safe) <= _lvl((x2, y2))


def test_trade_route_lengths_unchanged() -> None:
    """Повозки - по старому правилу колец: длина путей между городами та же."""
    c = wc.CITY_COORDS
    assert len(grid.safe_path(*c["ridge"], *c["docks"], by_level=False)) == 34
    assert len(grid.safe_path(*c["ridge"], *c["scorched"], by_level=False)) == 68


def test_fast_enough() -> None:
    started = time.perf_counter()
    grid.safe_path(-25, -5, 25, 5)
    assert time.perf_counter() - started < 1.0


def test_city_heals_silently() -> None:
    """2026-10-13: пришёл в город - здоровье полное (NULL), вне города - как было."""
    from types import SimpleNamespace

    from services import vitals_service

    hurt = SimpleNamespace(pos_x=wc.CITY_COORDS["ridge"][0], pos_y=wc.CITY_COORDS["ridge"][1], current_hp=12)
    vitals_service.heal_in_city(hurt)
    assert hurt.current_hp is None
    field = SimpleNamespace(pos_x=10, pos_y=10, current_hp=12)
    vitals_service.heal_in_city(field)
    assert field.current_hp == 12
