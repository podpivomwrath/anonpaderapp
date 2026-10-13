"""Безопасный путь верхом (2026-10-13): не заходит в кольца опаснее цели."""

import time

from game.world import grid
from game.world import world_config as wc


def _check(path, x1, y1, x2, y2):
    assert path[-1] == (x2, y2)
    prev = (x1, y1)
    for cell in path:
        assert grid.cells_between(*prev, *cell) == 1 and grid.in_bounds(*cell)
        prev = cell


def test_goes_around_inner_rings() -> None:
    # с запада на восток через центр: прямая режет IV кольцо, безопасный - нет
    x1, y1, x2, y2 = -20, 0, 20, 0
    straight = grid.line_path(x1, y1, x2, y2)
    safe = grid.safe_path(x1, y1, x2, y2)
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


def test_fast_enough() -> None:
    started = time.perf_counter()
    grid.safe_path(-25, -5, 25, 5)
    assert time.perf_counter() - started < 1.0
