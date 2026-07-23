"""Координатная сетка: расстояние, зоны сложности, города, ворота."""

import pytest

from game.world import grid
from game.world import world_config as wc


def test_chebyshev_distance() -> None:
    assert grid.chebyshev_distance(0, 0) == 0
    assert grid.chebyshev_distance(50, 50) == 50
    assert grid.chebyshev_distance(-50, 3) == 50
    assert grid.chebyshev_distance(7, -12) == 12


@pytest.mark.parametrize(
    "dist,expected",
    [(50, (1, 15)), (40, (1, 15)), (39, (16, 30)), (25, (16, 30)),
     (24, (31, 45)), (12, (31, 45)), (11, (46, 60)), (3, (46, 60)),
     (2, (60, 100)), (0, (60, 100))],
)
def test_zone_level_range_covers_full_map(dist: int, expected: tuple[int, int]) -> None:
    assert grid.zone_level_range(dist) == expected


def test_zone_table_covers_every_distance_without_gaps() -> None:
    for dist in range(0, 51):
        grid.zone_level_range(dist)  # не должно кидать/молча возвращать мусор


def test_city_region_at() -> None:
    assert grid.city_region_at(50, 50) == "ridge"
    assert grid.city_region_at(-50, 50) == "woods"
    assert grid.city_region_at(50, -50) == "docks"
    assert grid.city_region_at(-50, -50) == "scorched"
    assert grid.city_region_at(0, 0) is None
    assert grid.city_region_at(49, 50) is None


def test_gate_exit_position_steps_toward_center() -> None:
    assert grid.gate_exit_position(50, 50) == (49, 49)
    assert grid.gate_exit_position(-50, 50) == (-49, 49)
    assert grid.gate_exit_position(50, -50) == (49, -49)
    assert grid.gate_exit_position(-50, -50) == (-49, -49)


def test_clamp_respects_bounds() -> None:
    assert grid.clamp(51) == wc.BOUNDS_MAX
    assert grid.clamp(-51) == wc.BOUNDS_MIN
    assert grid.clamp(10) == 10
