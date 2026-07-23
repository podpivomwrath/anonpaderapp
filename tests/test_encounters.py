"""Спавн PvE-встреч стартового кольца: clamp уровня под игрока, флейвор."""

import random

import pytest

from game.world import encounters
from game.content_loader import load_starter_ring


def test_balanced_mob_stats_pool_matches_level() -> None:
    for level in (1, 5, 15):
        stats = encounters.balanced_mob_stats(level)
        pool = 75 + 3 * level
        total = stats.strength + stats.agility + stats.intellect + stats.vitality + stats.will
        assert total == pool


def test_starter_ring_loads_three_mobs_per_region() -> None:
    ring = load_starter_ring()
    assert set(ring) == {"ridge", "woods", "docks", "scorched"}
    for region, mobs in ring.items():
        assert len(mobs) == 3
        for mob in mobs:
            assert mob.flavor  # флейвор-текст присутствует
            assert mob.region == region
            assert (mob.zone_min, mob.zone_max) == (1, 15)


@pytest.mark.parametrize(
    "player_level,expected",
    [(1, 1), (10, 10), (15, 15), (30, 15), (100, 15)],  # clamp в зону 1-15
)
def test_mob_level_clamped_into_zone(player_level: int, expected: int) -> None:
    mob = load_starter_ring()["ridge"][0]  # zone 1-15
    assert encounters.mob_level_for_player(player_level, mob) == expected


def test_mob_level_respects_zone_floor() -> None:
    """Игрок ниже зоны → моб на нижней границе зоны (зашёл рано)."""

    class FakeMob:
        zone_min = 40
        zone_max = 45

    assert encounters.mob_level_for_player(5, FakeMob) == 40
    assert encounters.mob_level_for_player(42, FakeMob) == 42
    assert encounters.mob_level_for_player(60, FakeMob) == 45


def test_spawn_mob_returns_encounter_with_flavor() -> None:
    rng = random.Random(1)
    for region in ("ridge", "woods", "docks", "scorched"):
        enc = encounters.spawn_mob(2, region, player_level=5, rng=rng)
        assert enc.combatant.kind == "mob"
        assert enc.combatant.side == 1
        assert enc.combatant.tier == "grey"  # уровни 1-15 → серый тир
        assert enc.combatant.name
        assert enc.flavor  # флейвор для показа перед боем


def test_spawn_mob_level_matches_clamped_player_level() -> None:
    rng = random.Random(1)
    enc = encounters.spawn_mob(2, "ridge", player_level=8, rng=rng)
    assert enc.combatant.level == 8  # внутри зоны 1-15
    enc_high = encounters.spawn_mob(2, "ridge", player_level=99, rng=rng)
    assert enc_high.combatant.level == 15  # потолок зоны


def test_spawn_mob_picks_from_region_pool() -> None:
    rng = random.Random(42)
    ring = load_starter_ring()
    ridge_names = {m.name for m in ring["ridge"]}
    got = {encounters.spawn_mob(2, "ridge", 5, rng).combatant.name for _ in range(30)}
    assert got <= ridge_names
