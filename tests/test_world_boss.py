"""Мировые боссы (патч 104).

Правила, ради которых этот файл:
  1. босс не бьёт - заход это гонка урона, а не бой на выживание;
  2. урон всех заходов ложится на одно общее здоровье, и больше, чем у босса
     осталось, снять нельзя;
  3. пул разыгрывается ровно один раз и только между теми, кто бил;
  4. один заход в час, и к боссу не пускают тех, кто перерос его кольцо.
"""

import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
)
from game.economy import world_boss_config as wbc
from game.world import grid, world_boss
from models import (
    CharacterConsumable,
    CharacterTrophy,
    Inventory,
    WorldBoss,
    WorldBossMeter,
)
from services import world_boss_service as svc
from tests.conftest import combatant

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


# --- Контент и место ----------------------------------------------------------------


def test_bosses_have_names_and_flavor() -> None:
    defs = world_boss.boss_defs()
    assert len(defs) >= 4
    for boss in defs.values():
        assert boss.name.strip() and boss.flavor.strip(), boss.id


def test_every_ring_has_hp_and_rewards() -> None:
    for ring in wbc.RINGS:
        assert wbc.BOSS_HP[ring] > 0
        assert ring in wbc.ITEMS_BY_RING and ring in wbc.TROPHIES_BY_RING
        assert ring in wbc.HEALS_BY_RING and ring in wbc.COMBAT_ELIXIRS_BY_RING


def test_rings_match_the_map() -> None:
    """Уровень босса - потолок кольца, где он стоит: как у самых сильных
    мобов этого кольца."""
    for ring, (level, (lo, hi)) in wbc.RINGS.items():
        assert grid.zone_level_range(lo) == grid.zone_level_range(hi)
        assert grid.zone_level_range(lo)[1] == level, ring


def test_boss_stands_on_a_plain_cell_of_its_ring() -> None:
    from game.economy import fishing, mining

    rng = random.Random(5)
    for ring, (_level, (lo, hi)) in wbc.RINGS.items():
        for _ in range(300):
            x, y = world_boss.pick_cell(ring, rng)
            assert lo <= grid.chebyshev_distance(x, y) <= hi
            assert grid.city_region_at(x, y) is None
            assert fishing.lake_at(x, y) is None and mining.mine_at(x, y) is None


def test_overlevelled_players_are_kept_out() -> None:
    assert world_boss.can_attack(1, 1)
    assert world_boss.can_attack(15 + wbc.MAX_LEVEL_OVER_RING, 1)
    assert not world_boss.can_attack(16 + wbc.MAX_LEVEL_OVER_RING, 1)
    assert world_boss.can_attack(60, 4)


# --- Бой -------------------------------------------------------------------------


def test_boss_never_strikes_back() -> None:
    boss_def = next(iter(world_boss.boss_defs().values()))
    boss = world_boss.build_combatant(2, boss_def, 4, 20_000, 21_000)
    player = combatant(1, 0, strength=60, vitality=30, level=60)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    session.add(player)
    session.add(boss)
    hp_start = player.current_hp

    for _ in range(wbc.ATTEMPT_TURNS):
        session.tick_number += 1
        resolve_tick(session, {1: DeclaredAction(type=ActionType.ATTACK, target_id=2)}, random.Random(1))

    assert player.current_hp == hp_start
    assert boss.current_hp < 20_000
    assert boss.max_hp == 21_000


# --- Пул -----------------------------------------------------------------------------


def _pool_size(ring: int) -> int:
    return (
        wbc.ITEMS_BY_RING[ring] + sum(wbc.TROPHIES_BY_RING[ring].values())
        + wbc.HEALS_BY_RING[ring][1] + wbc.COMBAT_ELIXIRS_BY_RING[ring]
    )


def _handed_out(shares) -> int:
    return sum(
        len(s.items) + sum(s.trophies.values()) + sum(s.elixirs.values()) for s in shares.values()
    )


def test_whole_pool_is_handed_out_on_a_kill() -> None:
    shares = world_boss.split_pool(3, {1: 500, 2: 300, 3: 200}, 1.0, 10_000, random.Random(3))
    assert _handed_out(shares) == _pool_size(3)
    assert sum(s.xp for s in shares.values()) == 10_000


def test_xp_follows_damage_exactly() -> None:
    shares = world_boss.split_pool(2, {1: 750, 2: 250}, 1.0, 10_000, random.Random(3))
    assert shares[1].xp == 7_500 and shares[2].xp == 2_500


def test_escaped_boss_pays_its_removed_share() -> None:
    half = world_boss.split_pool(4, {1: 1}, 0.5, 10_000, random.Random(3))
    assert half[1].xp == 5_000
    assert _handed_out(half) < _pool_size(4)


def test_bigger_damage_wins_more_lots() -> None:
    rng = random.Random(11)
    wins = Counter()
    for _ in range(300):
        shares = world_boss.split_pool(1, {1: 900, 2: 100}, 1.0, 0, rng)
        for cid, share in shares.items():
            wins[cid] += len(share.items) + sum(share.trophies.values())
    assert wins[1] > wins[2] * 5
    assert wins[2] > 0, "у слабого вклада тоже есть шанс"


def test_nobody_without_damage_gets_anything() -> None:
    shares = world_boss.split_pool(1, {1: 100, 2: 0}, 1.0, 1_000, random.Random(1))
    assert set(shares) == {1}
    assert world_boss.split_pool(1, {}, 1.0, 1_000, random.Random(1)) == {}


# --- Появление ----------------------------------------------------------------------


async def test_boss_appears_when_the_meter_fills(db_session) -> None:
    rng = random.Random(1)
    for _ in range(wbc.EXPLORATIONS_PER_SPAWN - 1):
        assert await svc.record_exploration(db_session, rng, NOW) is None
    boss = await svc.record_exploration(db_session, rng, NOW)

    assert boss is not None and boss.status == svc.ACTIVE
    assert boss.hp == boss.max_hp == wbc.BOSS_HP[boss.ring]
    assert boss.expires_at == NOW + timedelta(hours=wbc.LIFETIME_HOURS)
    assert (await db_session.get(WorldBossMeter, 1)).explorations == 0


async def test_only_one_boss_at_a_time(db_session) -> None:
    rng = random.Random(1)
    await svc.spawn(db_session, rng, NOW)
    for _ in range(wbc.EXPLORATIONS_PER_SPAWN * 2):
        assert await svc.record_exploration(db_session, rng, NOW) is None


async def test_spawn_gap_holds_even_with_a_full_meter(db_session) -> None:
    rng = random.Random(1)
    db_session.add(WorldBossMeter(id=1, explorations=0, last_spawn_at=NOW))
    await db_session.flush()
    early = NOW + timedelta(hours=wbc.MIN_SPAWN_GAP_HOURS) - timedelta(minutes=1)
    for _ in range(wbc.EXPLORATIONS_PER_SPAWN + 5):
        assert await svc.record_exploration(db_session, rng, early) is None
    late = NOW + timedelta(hours=wbc.MIN_SPAWN_GAP_HOURS)
    assert await svc.record_exploration(db_session, rng, late) is not None


# --- Заход ----------------------------------------------------------------------------


async def _boss(db_session, ring: int = 2, hp: int | None = None) -> WorldBoss:
    x, y = world_boss.pick_cell(ring, random.Random(ring))
    boss = WorldBoss(
        boss_id="vein_grabber", ring=ring, level=world_boss.boss_level(ring), x=x, y=y,
        max_hp=wbc.BOSS_HP[ring], hp=hp if hp is not None else wbc.BOSS_HP[ring],
        status=svc.ACTIVE, spawned_at=NOW, expires_at=NOW + timedelta(hours=3),
    )
    db_session.add(boss)
    await db_session.flush()
    return boss


async def _at(make_character, boss, level: int = 25):
    character = await make_character(level=level)
    character.pos_x, character.pos_y = boss.x, boss.y
    return character


async def test_attempt_needs_the_right_cell_and_level(db_session, make_character) -> None:
    boss = await _boss(db_session, ring=2)
    away = await make_character(level=25)
    away.pos_x, away.pos_y = boss.x + 1, boss.y
    assert (await svc.start_attempt(db_session, away, boss.id, NOW)).reason == "not_here"

    too_strong = await _at(make_character, boss, level=30 + wbc.MAX_LEVEL_OVER_RING + 1)
    assert (await svc.start_attempt(db_session, too_strong, boss.id, NOW)).reason == "level"

    fits = await _at(make_character, boss, level=25)
    assert (await svc.start_attempt(db_session, fits, boss.id, NOW)).ok


async def test_one_attempt_per_hour(db_session, make_character) -> None:
    boss = await _boss(db_session)
    character = await _at(make_character, boss)
    assert (await svc.start_attempt(db_session, character, boss.id, NOW)).ok

    again = await svc.start_attempt(db_session, character, boss.id, NOW + timedelta(minutes=20))
    assert not again.ok and again.reason == "cooldown" and again.minutes_left == 40

    later = NOW + timedelta(minutes=wbc.ATTEMPT_COOLDOWN_MINUTES)
    assert (await svc.start_attempt(db_session, character, boss.id, later)).ok


async def test_expired_boss_takes_no_attempts(db_session, make_character) -> None:
    boss = await _boss(db_session)
    character = await _at(make_character, boss)
    late = NOW + timedelta(hours=3, seconds=1)
    assert (await svc.start_attempt(db_session, character, boss.id, late)).reason == "gone"
    assert await svc.active_boss(db_session, late) is None


# --- Урон и убийство -----------------------------------------------------------------


async def test_damage_is_shared_and_capped(db_session, make_character) -> None:
    boss = await _boss(db_session, hp=1_000)
    a = await _at(make_character, boss)
    b = await _at(make_character, boss)

    first = await svc.apply_damage(db_session, boss.id, a.id, 600, NOW)
    assert (first.hp, first.dealt, first.killed_now) == (400, 600, False)

    second = await svc.apply_damage(db_session, boss.id, b.id, 900, NOW)
    assert (second.hp, second.dealt, second.killed_now, second.over) == (0, 400, True, True)

    late = await svc.apply_damage(db_session, boss.id, a.id, 500, NOW)
    assert late.over and not late.killed_now and late.dealt == 0
    assert await svc.damage_by_character(db_session, boss.id) == {a.id: 600, b.id: 400}


async def test_kill_hands_the_pool_to_the_fighters(db_session, make_character) -> None:
    boss = await _boss(db_session, ring=1, hp=100)
    a = await _at(make_character, boss, level=10)
    b = await _at(make_character, boss, level=12)
    await svc.apply_damage(db_session, boss.id, a.id, 70, NOW)
    await svc.apply_damage(db_session, boss.id, b.id, 30, NOW)

    granted = await svc.distribute(db_session, boss, random.Random(4))

    assert [g.character_id for g in granted] == [a.id, b.id]  # по убыванию урона
    assert all(g.xp > 0 for g in granted)
    items = (await db_session.execute(select(Inventory))).scalars().all()
    trophies = (await db_session.execute(select(CharacterTrophy))).scalars().all()
    elixirs = (await db_session.execute(select(CharacterConsumable))).scalars().all()
    assert len(items) == wbc.ITEMS_BY_RING[1]
    assert sum(t.count for t in trophies) == sum(wbc.TROPHIES_BY_RING[1].values())
    assert sum(e.count for e in elixirs) == wbc.HEALS_BY_RING[1][1] + wbc.COMBAT_ELIXIRS_BY_RING[1]


async def test_escaped_boss_leaves_and_pays_a_part(db_session, make_character) -> None:
    boss = await _boss(db_session, ring=1)
    character = await _at(make_character, boss, level=10)
    await svc.apply_damage(db_session, boss.id, character.id, boss.max_hp // 2, NOW)

    assert await svc.expire_due(db_session, random.Random(1), NOW) == []
    ended = await svc.expire_due(db_session, random.Random(1), NOW + timedelta(hours=3))

    assert len(ended) == 1
    ended_boss, granted = ended[0]
    assert ended_boss.status == svc.ESCAPED
    assert svc.pool_share(ended_boss) == 0.5
    assert granted and granted[0].character_id == character.id
    # второй проход ничего не раздаёт повторно
    assert await svc.expire_due(db_session, random.Random(1), NOW + timedelta(hours=4)) == []
