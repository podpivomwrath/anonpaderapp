"""Патч гильдий 2026-10-17: Двор, мирная клетка во 2-м кольце, цена осады
от земли атакующего, щит после потери базы, Страж из Двора, недельные цели
по размеру гильдии."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from game.economy import guild_config as gc
from models import GuildBuilding, GuildWeekly
from services import (
    guild_boss_service,
    guild_quest_service,
    guild_service,
    guild_siege_service,
    guild_territory_service,
)
from services.guild_service import GuildError, now_utc
from tests.test_guilds import _add, _found, _held_base, _ore, _ring_cell


async def _rich(db, guild):
    await guild_service.treasury_add(db, guild.id, gold=10_000_000)
    for ore_id in ("salt_quartz", "taint_pyrite", "ashen_silver", "crimson_cluster"):
        await _ore(db, guild.id, ore_id, 400)


async def test_court_builds_up_to_five_and_counts_for_guild(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    await _rich(db_session, guild)
    with pytest.raises(GuildError, match="Во Дворе это не строят"):
        await guild_territory_service.start_court_build(db_session, leader, gc.B_TOTEM)
    for level in range(1, gc.COURT_MAX_LEVEL + 1):
        b = await guild_territory_service.start_court_build(db_session, leader, gc.B_CHAPEL)
        assert b.cell_id is None and b.guild_id == guild.id and b.upgrading_to == level
        with pytest.raises(GuildError, match="уже идёт стройка"):
            await guild_territory_service.start_court_build(db_session, leader, gc.B_FORGE)
        await guild_territory_service.complete_due(db_session, now_utc() + timedelta(days=30))
    with pytest.raises(GuildError, match="до 5 уровня"):
        await guild_territory_service.start_court_build(db_session, leader, gc.B_CHAPEL)
    levels = await guild_service.building_levels(db_session, guild.id)
    assert levels[gc.B_CHAPEL] == gc.COURT_MAX_LEVEL
    await db_session.refresh(leader)
    assert guild_service.perk(leader, "_chapel") == gc.COURT_MAX_LEVEL


async def test_court_warehouse_adds_to_map_warehouse(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    cell = await _held_base(db_session, guild, *_ring_cell(3))
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_WAREHOUSE, level=2))
    db_session.add(GuildBuilding(guild_id=guild.id, building=gc.B_WAREHOUSE, level=3))
    db_session.add(GuildBuilding(guild_id=guild.id, building=gc.B_FORGE, level=4))
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_FORGE, level=6))
    await db_session.flush()
    levels = await guild_service.building_levels(db_session, guild.id)
    assert levels[gc.B_WAREHOUSE] == 5 and levels[gc.B_FORGE] == 6


async def test_peaceful_ring_one_cell_and_no_siege(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    guild.level = 40
    enemy, enemy_leader = await _found(db_session, make_character, name="Чужие", tag="ЧЖ")
    x, y = _ring_cell(gc.PEACEFUL_RING_TIER)
    peaceful = await _held_base(db_session, enemy, x, y)
    await guild_service.treasury_add(db_session, guild.id, gold=10_000_000)
    with pytest.raises(GuildError, match="мирная"):
        await guild_siege_service.declare(db_session, leader, peaceful.id)
    # Вторую клетку в мирном кольце не поставить.
    await _held_base(db_session, guild, x + 1, y)
    from game.world import grid

    for yy in range(0, 31):
        for xx in range(0, 31):
            if grid.ring_tier(xx, yy) == gc.PEACEFUL_RING_TIER and guild_territory_service.claim_reason(xx, yy) is None \
                    and (xx, yy) not in ((x, y), (x + 1, y)):
                leader.pos_x, leader.pos_y = xx, yy
                with pytest.raises(GuildError, match="только 1 клетку"):
                    await guild_territory_service.plant_banner(db_session, leader, xx, yy)
                return
    pytest.fail("не нашлась вторая клетка мирного кольца")


def test_siege_cost_grows_with_attacker_land() -> None:
    from types import SimpleNamespace

    guild = SimpleNamespace(tree_nodes=[])
    base = guild_siege_service.siege_cost(guild, gc.BASE_OUTPOST)
    assert base == gc.SIEGE_COST[gc.BASE_OUTPOST]
    assert guild_siege_service.siege_cost(guild, gc.BASE_OUTPOST, held=6) == base * 4


async def test_losing_a_base_shields_the_rest(db_session, make_character) -> None:
    attacker, _a = await _found(db_session, make_character)
    attacker.level = 40
    defender, _d = await _found(db_session, make_character, name="Защитники", tag="ЗЩ")
    lost = await _held_base(db_session, defender, *_ring_cell(3))
    other = await _held_base(db_session, defender, *_ring_cell(4))
    siege = guild_siege_service.GuildSiege(
        attacker_guild_id=attacker.id, defender_guild_id=defender.id, cell_id=lost.id,
        x=lost.x, y=lost.y, declared_at=now_utc(), starts_at=now_utc(), status="running",
    )
    db_session.add(siege)
    await db_session.flush()
    outcome = await guild_siege_service.finish(db_session, siege.id, attackers_won=True)
    assert outcome.captured
    await db_session.refresh(other)
    left = guild_service.aware(other.shield_until) - now_utc()
    assert left > timedelta(hours=gc.LOSS_SHIELD_HOURS - 1)


async def test_court_boss_without_citadel_pays_less(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    await _ore(db_session, guild.id, gc.BOSS_SUMMON_ORE[0], gc.BOSS_SUMMON_ORE[1])
    await guild_service.treasury_add(db_session, guild.id, gold=gc.BOSS_SUMMON_GOLD)
    boss = await guild_boss_service.summon(db_session, leader)
    assert boss.court
    leader.pos_x, leader.pos_y = _city()  # из любого города (2026-10-20)
    assert (await guild_boss_service.start_attempt(db_session, leader, boss.id)).ok
    await guild_boss_service.apply_damage(db_session, boss.id, leader.id, 10**9)
    result = await guild_boss_service.distribute(db_session, boss)
    assert result.treasury_gold == round(gc.BOSS_TREASURY_GOLD * gc.BOSS_COURT_REWARD)


async def test_weekly_targets_scale_and_grow_on_join(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    rows = await guild_quest_service.ensure_weekly(db_session, guild.id)
    first = {r.metric: r.target for r in rows}
    for metric, target in first.items():
        assert target == gc.weekly_target(gc.QUEST_METRICS[metric][3], 1)
    for _ in range(12):
        await _add(db_session, make_character, guild)
    rows = (await db_session.scalars(select(GuildWeekly).where(GuildWeekly.guild_id == guild.id))).all()
    for r in rows:
        assert r.target == gc.weekly_target(gc.QUEST_METRICS[r.metric][3], 13) > first[r.metric]
    assert gc.weekly_target(60, 18) > 60 * 2 * 18


async def test_boss_difficulty_scales_hp_and_reward(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    await _ore(db_session, guild.id, gc.BOSS_SUMMON_ORE[0], gc.BOSS_SUMMON_ORE[1])
    await guild_service.treasury_add(db_session, guild.id, gold=gc.BOSS_SUMMON_GOLD)
    with pytest.raises(guild_service.GuildError):
        await guild_boss_service.summon(db_session, leader, 9)
    boss = await guild_boss_service.summon(db_session, leader, 3)
    _name, hp_mult, reward = gc.BOSS_DIFFICULTIES[3]
    assert boss.max_hp == round(gc.BOSS_MIN_HP * hp_mult)
    assert "(" in guild_boss_service.boss_title(boss)
    leader.pos_x, leader.pos_y = _city()
    assert (await guild_boss_service.start_attempt(db_session, leader, boss.id)).ok
    await guild_boss_service.apply_damage(db_session, boss.id, leader.id, 10**9)
    result = await guild_boss_service.distribute(db_session, boss)
    assert result.treasury_gold == round(gc.BOSS_TREASURY_GOLD * gc.BOSS_COURT_REWARD * reward)


async def test_court_boss_only_from_a_city(db_session, make_character) -> None:
    from game.world import grid

    guild, leader = await _found(db_session, make_character)
    await _ore(db_session, guild.id, gc.BOSS_SUMMON_ORE[0], gc.BOSS_SUMMON_ORE[1])
    await guild_service.treasury_add(db_session, guild.id, gold=gc.BOSS_SUMMON_GOLD)
    boss = await guild_boss_service.summon(db_session, leader)
    leader.pos_x, leader.pos_y = 7, 7
    assert grid.city_region_at(7, 7) is None
    assert not (await guild_boss_service.start_attempt(db_session, leader, boss.id)).ok
    leader.pos_x, leader.pos_y = _city()
    assert (await guild_boss_service.start_attempt(db_session, leader, boss.id)).ok


def _city() -> tuple[int, int]:
    from game.world import grid

    return next((x, y) for x in range(-30, 31) for y in range(-30, 31) if grid.city_region_at(x, y))


def test_citadel_boss_reachable_from_its_cell_or_any_city() -> None:
    from types import SimpleNamespace as N

    boss = N(court=False, x=7, y=7)
    assert guild_boss_service.can_reach(boss, N(pos_x=7, pos_y=7))
    assert guild_boss_service.can_reach(boss, N(pos_x=_city()[0], pos_y=_city()[1]))
    assert not guild_boss_service.can_reach(boss, N(pos_x=8, pos_y=7))
    court = N(court=True, x=0, y=0)
    assert not guild_boss_service.can_reach(court, N(pos_x=7, pos_y=7))
