"""Спавн PvE-встреч по кольцам карты (патч 15: все 5 колец, выбор по dist)."""

import random

import pytest

from game.world import encounters
from game.content_loader import load_bestiary, load_starter_ring


def test_balanced_mob_stats_pool_matches_level() -> None:
    """Патч 26: распределение специализировано, независимое округление 5
    бакетов даёт сумму НЕ строго равную пулу — допуск в несколько очков."""
    for level in (1, 5, 15):
        stats = encounters.balanced_mob_stats(level)
        pool = 75 + 3 * level
        total = stats.strength + stats.agility + stats.intellect + stats.vitality + stats.will
        assert abs(total - pool) <= 3


def test_balanced_mob_stats_specializes_primary_stat() -> None:
    """Патч 26: основной боевой стат получает ~45% бюджета, VIT — ~30%,
    остальные два боевых — по крохам (~8.33% каждый)."""
    stats = encounters.balanced_mob_stats(16, primary_stat="agi")
    pool = 75 + 3 * 16
    assert stats.agility == round(pool * 0.45)
    assert stats.vitality == round(pool * 0.30)
    assert stats.strength == round(pool * 0.0833)
    assert stats.intellect == round(pool * 0.0833)
    assert stats.will == round(pool * 0.0833)
    assert stats.agility > stats.strength
    assert stats.agility > stats.intellect


def test_balanced_mob_stats_defaults_to_str_primary() -> None:
    stats = encounters.balanced_mob_stats(10)
    pool = 75 + 3 * 10
    assert stats.strength == round(pool * 0.45)


def test_starter_ring_loads_three_mobs_per_region() -> None:
    ring = load_starter_ring()
    assert set(ring) == {"ridge", "woods", "docks", "scorched"}
    for region, mobs in ring.items():
        assert len(mobs) == 3
        for mob in mobs:
            assert mob.flavor  # флейвор-текст присутствует
            assert mob.region == region
            assert (mob.zone_min, mob.zone_max) == (1, 15)


def test_bestiary_merges_all_rings_per_region() -> None:
    bestiary = load_bestiary()
    assert set(bestiary) == {"ridge", "woods", "docks", "scorched", "any"}
    for region in ("ridge", "woods", "docks", "scorched"):
        assert len(bestiary[region]) == 12  # 4 кольца × 3 моба
        zones = {(m.zone_min, m.zone_max) for m in bestiary[region]}
        assert zones == {(1, 15), (16, 30), (31, 45), (46, 60)}
    assert len(bestiary["any"]) == 4
    assert all((m.zone_min, m.zone_max) == (60, 100) for m in bestiary["any"])


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
        enc = encounters.spawn_mob(2, region, player_level=5, dist=45, rng=rng)
        assert enc.combatant.kind == "mob"
        assert enc.combatant.side == 1
        assert enc.combatant.tier == "grey"  # уровни 1-15 → серый тир
        assert enc.combatant.name
        assert enc.flavor  # флейвор для показа перед боем


def test_spawn_mob_level_matches_clamped_player_level() -> None:
    rng = random.Random(1)
    enc = encounters.spawn_mob(2, "ridge", player_level=8, dist=45, rng=rng)
    assert enc.combatant.level == 8  # внутри зоны 1-15
    enc_high = encounters.spawn_mob(2, "ridge", player_level=99, dist=45, rng=rng)
    assert enc_high.combatant.level == 15  # потолок зоны (dist 45 => кольцо 1-15)


def test_spawn_mob_picks_from_region_pool() -> None:
    rng = random.Random(42)
    ring = load_starter_ring()
    ridge_names = {m.name for m in ring["ridge"]}
    got = {encounters.spawn_mob(2, "ridge", 5, dist=45, rng=rng).combatant.name for _ in range(30)}
    assert got <= ridge_names


def test_spawn_mob_picks_from_current_ring_not_home_region_pool() -> None:
    """dist=30 -> кольцо 16-30 (ZONE_TABLE: dist 25-39), патч 15: моб приходит
    из соответствующего файла бестиария, даже если игрок 5 уровня (уровень
    клампится ВВЕРХ до 16)."""
    rng = random.Random(7)
    bestiary = load_bestiary()
    ring16_30_names = {m.name for m in bestiary["ridge"] if (m.zone_min, m.zone_max) == (16, 30)}
    enc = encounters.spawn_mob(2, "ridge", player_level=5, dist=30, rng=rng)
    assert enc.combatant.name in ring16_30_names
    assert enc.combatant.level == 16  # clamp вверх — зашёл рано


def test_spawn_mob_low_level_player_in_high_ring_clamps_to_ring_floor() -> None:
    """Патч 15, техзаметки: игрок 5 уровня, зашедший в кольцо 46-60 (dist 3-11),
    должен встретить моба 46 уровня (нижняя граница), а не своего уровня."""
    rng = random.Random(11)
    enc = encounters.spawn_mob(2, "ridge", player_level=5, dist=7, rng=rng)
    assert enc.combatant.level == 46


def test_spawn_mob_uses_content_primary_stat() -> None:
    """Патч 26: primary_stat боевого участника берётся из бестиария (не всегда
    STR), а не хардкодится."""
    rng = random.Random(1)
    ring = load_starter_ring()
    by_id = {m.id: m for mobs in ring.values() for m in mobs}
    for _ in range(20):
        enc = encounters.spawn_mob(2, "ridge", player_level=5, dist=45, rng=rng)
        mob_def = next(m for m in by_id.values() if m.name == enc.combatant.name)
        assert enc.combatant.primary_stat == mob_def.primary_stat


_STAT_FIELD = {"str": "strength", "agi": "agility", "int": "intellect"}


def test_spawn_mob_applies_base_and_ring_multiplier() -> None:
    """Патч 26: статы моба = специализированный пул × MOB_BASE_MULTIPLIER ×
    множитель кольца (кольцо 1-15 -> ×1.0, значит только базовый множитель)."""
    from game.combat import balance_config as bc

    rng = random.Random(1)
    enc = encounters.spawn_mob(2, "ridge", player_level=8, dist=45, rng=rng)
    field = _STAT_FIELD[enc.combatant.primary_stat]
    raw = encounters.balanced_mob_stats(8, enc.combatant.primary_stat)
    expected = round(getattr(raw, field) * bc.MOB_BASE_MULTIPLIER * 1.0)
    assert getattr(enc.combatant.stats, field) == expected


def test_spawn_mob_center_uses_any_region_regardless_of_home_region() -> None:
    """dist=1 (центр, кольцо 60+) — мобы общие, регион игрока не важен."""
    rng = random.Random(3)
    bestiary = load_bestiary()
    center_names = {m.name for m in bestiary["any"]}
    for region in ("ridge", "woods", "docks", "scorched"):
        enc = encounters.spawn_mob(2, region, player_level=70, dist=1, rng=rng)
        assert enc.combatant.name in center_names
        assert enc.combatant.level == 70
