"""Координатная сетка: расстояние, зоны сложности, города, ворота."""

import pytest

from game.world import grid
from game.world import world_config as wc


def test_monolith_distance_is_round_euclid() -> None:
    assert grid.monolith_distance(0, 0) == 0
    assert grid.monolith_distance(0, 30) == 30
    assert grid.monolith_distance(21, 21) == 30
    assert grid.monolith_distance(3, 4) == 5
    assert grid.monolith_distance(1, 1) == 1


@pytest.mark.parametrize(
    "dist,expected",
    [(30, (1, 15)), (24, (1, 15)), (23, (16, 30)), (15, (16, 30)),
     (14, (31, 45)), (7, (31, 45)), (6, (46, 60)), (2, (46, 60)),
     (1, (60, 60)), (0, (60, 60))],
)
def test_zone_level_range_covers_full_map(dist: int, expected: tuple[int, int]) -> None:
    assert grid.zone_level_range(dist) == expected


def test_zone_table_covers_every_distance_without_gaps() -> None:
    """Каждое расстояние 0..WORLD_RADIUS - ровно в одном кольце, кольца идут
    подряд без дыр, а уровни растут к центру."""
    covered = sorted(d for lo, hi, _ in wc.ZONE_TABLE for d in range(lo, hi + 1))
    assert covered == list(range(0, wc.WORLD_RADIUS + 1))
    previous_max = 0
    for dist in range(wc.WORLD_RADIUS, -1, -1):
        lo, hi = grid.zone_level_range(dist)
        assert 1 <= lo <= hi <= 60
        assert hi >= previous_max
        previous_max = hi


def test_city_region_at() -> None:
    assert grid.city_region_at(0, 30) == "ridge"
    assert grid.city_region_at(-30, 0) == "woods"
    assert grid.city_region_at(30, 0) == "docks"
    assert grid.city_region_at(0, -30) == "scorched"
    assert grid.city_region_at(0, 0) is None
    assert grid.city_region_at(1, 30) is None


def test_cities_stand_on_the_rim_of_their_own_region() -> None:
    from game.world.location_types import region_for

    for region, (x, y) in wc.CITY_COORDS.items():
        assert grid.monolith_distance(x, y) == wc.WORLD_RADIUS
        assert region_for(x, y) == region


def test_in_bounds_is_a_circle() -> None:
    assert grid.in_bounds(0, 30) is True
    assert grid.in_bounds(21, 21) is True
    assert grid.in_bounds(22, 22) is False
    assert grid.in_bounds(30, 30) is False
    assert grid.in_bounds(0, -31) is False
    assert grid.in_bounds(0, 0) is True


def test_clamp_respects_bounds() -> None:
    assert grid.clamp(51) == wc.BOUNDS_MAX
    assert grid.clamp(-51) == wc.BOUNDS_MIN
    assert grid.clamp(10) == 10


# --- mob_level_at (патч 36): уровень квестового моба/события — по клетке ---


def test_mob_level_at_clamps_into_zone() -> None:
    assert grid.mob_level_at(0, 28, player_level=60) == 15  # дальнее кольцо, потолок 15
    assert grid.mob_level_at(0, 28, player_level=1) == 1  # внутри зоны — как есть
    assert grid.mob_level_at(1, 0, player_level=1) == 60  # у Монолита — пол зоны 60


def test_mob_level_at_matches_zone_level_range() -> None:
    for dist in (0, 5, 12, 20, 28):
        zone_min, zone_max = grid.zone_level_range(dist)
        assert grid.mob_level_at(dist, 0, player_level=1) == zone_min
        assert grid.mob_level_at(dist, 0, player_level=999) == zone_max
