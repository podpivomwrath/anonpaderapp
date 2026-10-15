"""Спавн PvE-встреч по кольцам карты (патч 15: все 5 колец, выбор по dist)."""

import random

import pytest

from game.combat import balance_config as bc
from game.world import encounters
from game.world import world_config as wc
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
    """Патч 28: основной боевой стат получает ~38% бюджета (было 45% в патче
    26 — перебор), VIT — ~32%, остальные два боевых — по 10% каждый."""
    stats = encounters.balanced_mob_stats(16, primary_stat="agi")
    pool = 75 + 3 * 16
    assert stats.agility == round(pool * 0.38)
    assert stats.vitality == round(pool * 0.32)
    assert stats.strength == round(pool * 0.10)
    assert stats.intellect == round(pool * 0.10)
    assert stats.will == round(pool * 0.10)
    assert stats.agility > stats.strength
    assert stats.agility > stats.intellect


def test_balanced_mob_stats_defaults_to_str_primary() -> None:
    stats = encounters.balanced_mob_stats(10)
    pool = 75 + 3 * 10
    assert stats.strength == round(pool * 0.38)


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
    assert all((m.zone_min, m.zone_max) == (bc.MAX_LEVEL, bc.MAX_LEVEL) for m in bestiary["any"])


def test_cell_level_grows_toward_monolith_within_ring() -> None:
    """2026-10-15: уровень - от клетки. Внешний край кольца - нижняя граница,
    внутренний - верхняя, между ними растёт к Монолиту."""
    for d_lo, d_hi, (l_lo, l_hi) in wc.ZONE_TABLE:
        assert wc.cell_base_level(d_hi) == l_lo or l_lo == l_hi
        assert wc.cell_base_level(d_lo) == l_hi
        levels = [wc.cell_base_level(d) for d in range(d_hi, d_lo - 1, -1)]
        assert levels == sorted(levels)


def test_cell_level_range_spread_stays_in_ring() -> None:
    for d_lo, d_hi, (l_lo, l_hi) in wc.ZONE_TABLE:
        for d in range(d_lo, d_hi + 1):
            lo, hi = wc.cell_level_range(d)
            assert l_lo <= lo <= hi <= l_hi
            assert hi - lo <= 2 * wc.MOB_LEVEL_SPREAD


def test_spawn_mob_returns_encounter_with_flavor() -> None:
    rng = random.Random(1)
    for region in ("ridge", "woods", "docks", "scorched"):
        enc = encounters.spawn_mob(2, region, player_level=5, dist=27, rng=rng)
        assert enc.combatant.kind == "mob"
        assert enc.combatant.side == 1
        assert enc.combatant.tier == "grey"  # уровни 1-15 → серый тир
        assert enc.combatant.name
        assert enc.flavor  # флейвор для показа перед боем


def test_spawn_mob_level_ignores_player_level() -> None:
    """Уровень моба - от клетки, игрок 1 и 60 уровня встречают одинаковых."""
    lo, hi = wc.cell_level_range(27)
    for player_level in (1, 60):
        rng = random.Random(1)
        enc = encounters.spawn_mob(2, "ridge", player_level=player_level, dist=27, rng=rng)
        assert lo <= enc.combatant.level <= hi


def test_spawn_mob_picks_from_region_pool() -> None:
    rng = random.Random(42)
    ring = load_starter_ring()
    ridge_names = {m.name for m in ring["ridge"]}
    got = {encounters.spawn_mob(2, "ridge", 5, dist=27, rng=rng).combatant.name for _ in range(30)}
    assert got <= ridge_names


def test_spawn_mob_picks_from_current_ring_not_home_region_pool() -> None:
    """dist=20 -> кольцо 16-30: моб из бестиария этого кольца и уровня клетки."""
    rng = random.Random(7)
    bestiary = load_bestiary()
    ring16_30_names = {m.name for m in bestiary["ridge"] if (m.zone_min, m.zone_max) == (16, 30)}
    enc = encounters.spawn_mob(2, "ridge", player_level=5, dist=20, rng=rng)
    assert enc.combatant.name in ring16_30_names
    lo, hi = wc.cell_level_range(20)
    assert lo <= enc.combatant.level <= hi


def test_spawn_mob_uses_content_primary_stat() -> None:
    """Патч 26: primary_stat боевого участника берётся из бестиария (не всегда
    STR), а не хардкодится."""
    rng = random.Random(1)
    ring = load_starter_ring()
    by_id = {m.id: m for mobs in ring.values() for m in mobs}
    for _ in range(20):
        enc = encounters.spawn_mob(2, "ridge", player_level=5, dist=27, rng=rng)
        mob_def = next(m for m in by_id.values() if m.name == enc.combatant.name)
        assert enc.combatant.primary_stat == mob_def.primary_stat


_STAT_FIELD = {"str": "strength", "agi": "agility", "int": "intellect"}


def test_spawn_mob_applies_damage_multiplier_to_primary_stat(monkeypatch) -> None:
    """Патч 28: боевые статы (в т.ч. основной) масштабируются MOB_DAMAGE_MULTIPLIER
    × кольцо-вполовину (кольцо 1-15 -> ×1.0, значит только базовый множитель)."""
    from game.combat import balance_config as bc

    monkeypatch.setattr(encounters, "roll_stat_spread", lambda rng: (1.0, 1.0))
    rng = random.Random(1)
    enc = encounters.spawn_mob(2, "ridge", player_level=8, dist=27, rng=rng)
    field = _STAT_FIELD[enc.combatant.primary_stat]
    raw = encounters.balanced_mob_stats(enc.combatant.level, enc.combatant.primary_stat)
    expected = round(getattr(raw, field) * bc.MOB_DAMAGE_MULTIPLIER * 1.0)
    assert getattr(enc.combatant.stats, field) == expected


def test_spawn_mob_applies_hp_multiplier_to_vitality(monkeypatch) -> None:
    """Патч 28: VIT масштабируется отдельным MOB_HP_MULTIPLIER (кольцо целиком,
    без деления пополам, в отличие от боевых статов)."""
    from game.combat import balance_config as bc

    monkeypatch.setattr(encounters, "roll_stat_spread", lambda rng: (1.0, 1.0))
    rng = random.Random(1)
    enc = encounters.spawn_mob(2, "ridge", player_level=8, dist=27, rng=rng)
    raw = encounters.balanced_mob_stats(enc.combatant.level, enc.combatant.primary_stat)
    expected = round(raw.vitality * bc.MOB_HP_MULTIPLIER * 1.0)
    assert enc.combatant.stats.vitality == expected


def test_spawn_mob_ring_multiplier_is_halved_for_damage(monkeypatch) -> None:
    """Патч 28: в кольце 16-30 (×1.15) VIT получает множитель целиком, а
    боевые статы — только половину надбавки (1 + 0.15*0.5 = 1.075)."""
    from game.combat import balance_config as bc

    monkeypatch.setattr(encounters, "roll_stat_spread", lambda rng: (1.0, 1.0))
    rng = random.Random(5)
    enc = encounters.spawn_mob(2, "ridge", player_level=20, dist=20, rng=rng)  # кольцо 16-30
    field = _STAT_FIELD[enc.combatant.primary_stat]
    raw = encounters.balanced_mob_stats(enc.combatant.level, enc.combatant.primary_stat)

    ring_mult = bc.MOB_RING_MULTIPLIERS[(16, 30)]
    expected_vit = round(raw.vitality * bc.MOB_HP_MULTIPLIER * ring_mult)
    expected_dmg_stat = round(getattr(raw, field) * bc.MOB_DAMAGE_MULTIPLIER * (1 + (ring_mult - 1) * 0.5))

    assert enc.combatant.stats.vitality == expected_vit
    assert getattr(enc.combatant.stats, field) == expected_dmg_stat


def test_spawn_mob_center_uses_any_region_regardless_of_home_region() -> None:
    """dist=1 (центр, кольцо == MAX_LEVEL) — мобы общие, регион игрока не важен."""
    rng = random.Random(3)
    bestiary = load_bestiary()
    center_names = {m.name for m in bestiary["any"]}
    for region in ("ridge", "woods", "docks", "scorched"):
        enc = encounters.spawn_mob(2, region, player_level=bc.MAX_LEVEL, dist=1, rng=rng)
        assert enc.combatant.name in center_names
        assert enc.combatant.level == bc.MAX_LEVEL



def test_stat_spread_is_mild_and_never_glass_cannon() -> None:
    """2026-10-15: разброс статов небольшой, и мало здоровья не идёт вместе
    с большим уроном: урон сдвигается в обратную сторону вдвое слабее."""
    rng = random.Random(3)
    for _ in range(2000):
        hp, dmg = encounters.roll_stat_spread(rng)
        assert 1 - encounters.HP_SPREAD <= hp <= 1 + encounters.HP_SPREAD
        assert dmg <= (1 + encounters.HP_SPREAD / 2) * (1 + encounters.DMG_JITTER) + 1e-9
        assert hp * dmg >= 0.85  # общая опасность почти не плавает
