"""Гильдии: основание, состав, казна и склад, задания, территория, постройки,
осады, древо, сезоны, страж цитадели."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.economy import guild_config as gc
from game.guild import tree as guild_tree
from models import (
    CharacterOre,
    Guild,
    GuildBuilding,
    GuildCell,
    GuildDaily,
    GuildMember,
    GuildSiege,
    Inventory,
    Item,
    MineVein,
)
from services import (
    guild_boss_service,
    guild_quest_service,
    guild_season_service,
    guild_service,
    guild_siege_service,
    guild_territory_service,
    guild_tree_service,
    wallet_service,
)
from services.guild_service import GuildError


async def _found(db, make_character, name="Пепельный Орден", tag="ПО", gold=0):
    leader = await make_character(level=30, donate=gc.FOUND_COST_GEMS, farm=gold)
    guild = await guild_service.create(db, leader, name, tag)
    return guild, leader


async def _add(db, make_character, guild, rank=gc.RANK_RECRUIT, level=30):
    character = await make_character(level=level)
    await guild_service._join(db, guild, character)
    member = await guild_service.membership(db, character.id)
    member.rank = rank
    return character


async def _ore(db, guild_id, ore_id, count, grade="common"):
    await guild_service.add_guild_ore(db, guild_id, ore_id, grade, count)


# --- Основание и состав --------------------------------------------------------


async def test_found_costs_gems_and_level(db_session, make_character) -> None:
    poor = await make_character(level=30, donate=10)
    with pytest.raises(GuildError):
        await guild_service.create(db_session, poor, "Орден", "ОР")
    young = await make_character(level=5, donate=5000)
    with pytest.raises(GuildError):
        await guild_service.create(db_session, young, "Орден", "ОР")
    guild, leader = await _found(db_session, make_character)
    wallet = await wallet_service.get_wallet(db_session, leader.id)
    assert wallet.donate_currency == 0
    assert leader.guild_id == guild.id
    member = await guild_service.membership(db_session, leader.id)
    assert member.rank == gc.RANK_LEADER
    other = await make_character(level=30, donate=gc.FOUND_COST_GEMS)
    with pytest.raises(GuildError):
        await guild_service.create(db_session, other, "пепельный орден", "ХХ")


async def test_invite_accept_and_rejoin_cooldown(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    newbie = await make_character(level=10)
    member = await guild_service.membership(db_session, leader.id)
    assert member is not None
    target = await guild_service.invite(db_session, leader, newbie.name)
    assert target.id == newbie.id
    await guild_service.accept_invite(db_session, newbie, guild.id)
    assert newbie.guild_id == guild.id
    await guild_service.leave(db_session, newbie)
    assert newbie.guild_id is None
    await guild_service.invite(db_session, leader, newbie.name)
    with pytest.raises(GuildError, match="через"):
        await guild_service.accept_invite(db_session, newbie, guild.id)


async def test_application_flow(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    applicant = await make_character(level=12)
    await guild_service.apply(db_session, applicant, guild.id)
    apps = await guild_service.applications_of(db_session, guild.id)
    assert [c.id for _i, c in apps] == [applicant.id]
    recruit = await _add(db_session, make_character, guild)
    with pytest.raises(GuildError):
        await guild_service.accept_application(db_session, recruit, applicant.id)
    await guild_service.accept_application(db_session, leader, applicant.id)
    assert applicant.guild_id == guild.id


async def test_treasurer_rights(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    treasurer = await _add(db_session, make_character, guild, gc.RANK_TREASURER)
    other_treasurer = await _add(db_session, make_character, guild, gc.RANK_TREASURER)
    officer = await _add(db_session, make_character, guild, gc.RANK_OFFICER)
    with pytest.raises(GuildError):
        await guild_service.kick(db_session, treasurer, leader.id)
    with pytest.raises(GuildError):
        await guild_service.kick(db_session, treasurer, other_treasurer.id)
    with pytest.raises(GuildError):
        await guild_service.disband(db_session, treasurer)
    await guild_service.kick(db_session, treasurer, officer.id)
    assert officer.guild_id is None
    # Казна - за казначеем, как за главой.
    await guild_service.treasury_add(db_session, guild.id, gold=1000)
    await guild_service.withdraw(db_session, treasurer, "gold", 400)
    assert (await wallet_service.get_wallet(db_session, treasurer.id)).farm_currency == 400


async def test_leader_cannot_leave_with_members(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    other = await _add(db_session, make_character, guild)
    with pytest.raises(GuildError):
        await guild_service.leave(db_session, leader)
    await guild_service.transfer_leadership(db_session, leader, other.id)
    await guild_service.leave(db_session, leader)
    assert (await guild_service.membership(db_session, other.id)).rank == gc.RANK_LEADER


async def test_member_cap(db_session, make_character) -> None:
    assert gc.member_cap(1) == 30 and gc.member_cap(21) == 50 and gc.member_cap(100) == 50


async def test_disband_returns_treasury_to_leader(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    await guild_service.treasury_add(db_session, guild.id, gold=500, gems=7)
    await _ore(db_session, guild.id, "salt_quartz", 3)
    member = await _add(db_session, make_character, guild)
    former = await guild_service.disband(db_session, leader)
    assert set(former) == {leader.id, member.id}
    wallet = await wallet_service.get_wallet(db_session, leader.id)
    assert wallet.farm_currency == 500 and wallet.donate_currency == 7
    ore = await db_session.scalar(select(CharacterOre).where(CharacterOre.character_id == leader.id))
    assert ore.count == 3
    assert leader.guild_id is None and member.guild_id is None


# --- Казна и склад ---------------------------------------------------------------


async def test_deposit_and_spend(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character, gold=2000)
    recruit = await _add(db_session, make_character, guild)
    await wallet_service.deposit(db_session, recruit.id, "farm", 300)
    await guild_service.deposit(db_session, recruit, "gold", 300)
    with pytest.raises(GuildError):
        await guild_service.withdraw(db_session, recruit, "gold", 100)
    await guild_service.treasury_spend(db_session, guild.id, gold=200)
    await db_session.refresh(guild)
    assert guild.treasury_gold == 100
    with pytest.raises(GuildError, match="не хватает"):
        await guild_service.treasury_spend(db_session, guild.id, gold=101)


async def test_warehouse_ore_and_items(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    db_session.add(CharacterOre(character_id=leader.id, ore_id="salt_quartz", grade="rare", count=5))
    await db_session.flush()
    await guild_service.deposit_ore(db_session, leader, "salt_quartz", "rare", 4)
    stock = await guild_service.ore_stock(db_session, guild.id)
    assert [(o.ore_id, o.count) for o in stock] == [("salt_quartz", 4)]
    with pytest.raises(GuildError):
        await guild_service.deposit_ore(db_session, leader, "salt_quartz", "rare", 4)
    item = Item(name="Меч", slot="weapon", base_stats={"str": 3})
    bound = Item(name="Игла", slot="weapon", base_stats={"str": 9}, bound=True)
    db_session.add_all([item, bound])
    await db_session.flush()
    db_session.add_all([
        Inventory(character_id=leader.id, item_id=item.id),
        Inventory(character_id=leader.id, item_id=bound.id),
    ])
    await db_session.flush()
    await guild_service.deposit_item(db_session, leader, item.id)
    with pytest.raises(GuildError, match="привязана"):
        await guild_service.deposit_item(db_session, leader, bound.id)
    assert [i.id for i in await guild_service.stored_items(db_session, guild.id)] == [item.id]
    await guild_service.withdraw_item(db_session, leader, item.id)
    assert await db_session.scalar(
        select(Inventory).where(Inventory.character_id == leader.id, Inventory.item_id == item.id)
    ) is not None


async def test_spend_ore_takes_worst_grades_first(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    await _ore(db_session, guild.id, "salt_quartz", 2, "epic")
    await _ore(db_session, guild.id, "salt_quartz", 3, "common")
    await guild_service.spend_guild_ore(db_session, guild.id, "salt_quartz", 4)
    stock = {o.grade: o.count for o in await guild_service.ore_stock(db_session, guild.id)}
    assert stock == {"epic": 1}


# --- Слава и задания -----------------------------------------------------------------


async def test_fame_levels_up(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    result = await guild_service.add_fame(db_session, guild.id, gc.fame_to_next(1) + gc.fame_to_next(2) + 5)
    assert result.levels_gained == 2 and result.new_level == 3
    assert guild_service.tree_points_available(guild) == 2


async def test_guild_daily_and_weekly(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    dailies = await guild_quest_service.ensure_dailies(db_session, leader)
    assert len(dailies) == gc.DAILIES_PER_MEMBER
    metric = dailies[0].metric
    notices = await guild_quest_service.record(db_session, leader, metric, dailies[0].target)
    assert any("ежедневка" in n for n in notices)
    row = await db_session.scalar(select(GuildDaily).where(GuildDaily.id == dailies[0].id))
    assert row.completed
    member = await guild_service.membership(db_session, leader.id)
    assert member.contribution_total >= gc.DAILY_CONTRIBUTION
    weekly = await guild_quest_service.ensure_weekly(db_session, guild.id)
    assert len(weekly) == gc.WEEKLY_QUESTS
    target = weekly[0]
    await guild_quest_service.record(db_session, leader, target.metric, target.target * 2)
    await db_session.refresh(target)
    assert target.completed and target.progress == target.target
    tops = await guild_quest_service.contribution_tops(db_session, guild.id)
    assert tops["total"][0]["id"] == leader.id


async def test_record_without_guild_is_noop(db_session, make_character) -> None:
    loner = await make_character(level=10)
    assert await guild_quest_service.record(db_session, loner, "kill", 5) == []


# --- Территория ---------------------------------------------------------------------


def _ring_cell(tier: int) -> tuple[int, int]:
    from game.economy import fishing, mining
    from game.world import grid

    for y in range(0, 31):
        for x in range(0, 31):
            if grid.in_bounds(x, y) and grid.ring_tier(x, y) == tier and not fishing.is_lake(x, y) \
                    and not mining.is_mine(x, y) and grid.city_region_at(x, y) is None:
                return x, y
    raise AssertionError("нет клетки")


async def _held_base(db, guild, x, y, tier=gc.BASE_OUTPOST, mine_id=None):
    cell = GuildCell(guild_id=guild.id, x=x, y=y, status="held", base_tier=tier, mine_id=mine_id)
    db.add(cell)
    await db.flush()
    return cell


async def test_claim_rules(db_session, make_character) -> None:
    assert guild_territory_service.claim_reason(*_ring_cell(1)) is not None
    assert guild_territory_service.claim_reason(0, 0) is not None
    assert guild_territory_service.claim_reason(*_ring_cell(3)) is None


async def test_banner_and_claim_by_exploration(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    guild.level = 3
    x, y = _ring_cell(3)
    leader.pos_x, leader.pos_y = x, y
    with pytest.raises(GuildError):
        await guild_territory_service.plant_banner(db_session, leader, x, y)  # нет руды и золота
    await _ore(db_session, guild.id, "taint_pyrite", 15)
    await guild_service.treasury_add(db_session, guild.id, gold=gc.BANNER_COST_CELL)
    cell = await guild_territory_service.plant_banner(db_session, leader, x, y)
    assert cell.status == "claiming" and cell.claim_needed == gc.CLAIM_EXPLORATIONS
    outsider = await make_character(level=40)
    outsider.pos_x, outsider.pos_y = x, y
    await guild_territory_service.on_exploration(db_session, outsider)
    assert cell.claim_progress == 0
    for _ in range(gc.CLAIM_EXPLORATIONS):
        outcome = await guild_territory_service.on_exploration(db_session, leader)
    assert outcome.claimed is not None and cell.status == "held"
    # Теперь десятина: исследование чужака приносит золото в казну.
    await db_session.refresh(guild)
    before = guild.treasury_gold
    outcome = await guild_territory_service.on_exploration(db_session, outsider)
    await db_session.refresh(guild)
    assert outcome.tithe_gold == gc.TITHE_BY_RING[3] and guild.treasury_gold == before + outcome.tithe_gold


async def test_cell_slots_limit(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    guild.level = 1
    x, y = _ring_cell(2)
    leader.pos_x, leader.pos_y = x, y
    with pytest.raises(GuildError, match="слотов"):
        await guild_territory_service.plant_banner(db_session, leader, x, y)
    assert gc.cell_slots(40) == 5 and gc.mine_slots(19) == 0 and gc.mine_slots(20) == 1


async def test_claim_expires(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    cell = GuildCell(
        guild_id=guild.id, x=5, y=10, status="claiming", claim_needed=40,
        claim_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(cell)
    await db_session.flush()
    gone = await guild_territory_service.expire_claims(db_session)
    assert len(gone) == 1


async def test_build_and_complete(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    cell = await _held_base(db_session, guild, 5, 12)
    await _ore(db_session, guild.id, "salt_quartz", 50)
    await guild_service.treasury_add(db_session, guild.id, gold=10**6)
    building = await guild_territory_service.start_build(db_session, leader, cell.id, gc.B_CHAPEL)
    with pytest.raises(GuildError, match="идёт стройка"):
        await guild_territory_service.start_build(db_session, leader, cell.id, gc.B_FORGE)
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    done = await guild_territory_service.complete_due(db_session, later)
    assert done and building.level == 1
    assert leader.guild_perks.get("_chapel") == 1
    # Шахта - только на руднике; на заставе - не выше 3 уровня.
    with pytest.raises(GuildError, match="руднике"):
        await guild_territory_service.start_build(db_session, leader, cell.id, gc.B_SHAFT)
    building.level = 3
    with pytest.raises(GuildError, match="Выше"):
        await guild_territory_service.start_build(db_session, leader, cell.id, gc.B_CHAPEL)


async def test_base_slots(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    cell = await _held_base(db_session, guild, 5, 12)
    db_session.add_all([
        GuildBuilding(cell_id=cell.id, building=gc.B_TOTEM, level=1),
        GuildBuilding(cell_id=cell.id, building=gc.B_FORGE, level=1),
    ])
    await db_session.flush()
    with pytest.raises(GuildError, match="мест"):
        await guild_territory_service.start_build(db_session, leader, cell.id, gc.B_CHAPEL)


async def test_citadel_is_unique_and_gated(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    a = await _held_base(db_session, guild, 5, 12, tier=gc.BASE_FORT)
    await _held_base(db_session, guild, 6, 12, tier=gc.BASE_CITADEL)
    guild.level = 40
    with pytest.raises(GuildError, match="одна"):
        await guild_territory_service.start_base_upgrade(db_session, leader, a.id)


async def test_shaft_digs_into_warehouse(db_session, make_character) -> None:
    from game.economy import mining

    guild, _leader = await _found(db_session, make_character)
    mine = next(m for m in mining.all_mines() if m.tier == 3)
    cell = await _held_base(db_session, guild, mine.x, mine.y, mine_id=mine.id)
    cell.shaft_checked_at = datetime.now(timezone.utc) - timedelta(hours=10)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_SHAFT, level=3))
    db_session.add(MineVein(mine_id=mine.id, ore_count=3))
    await db_session.flush()
    mined = await guild_territory_service.shaft_tick(db_session, random.Random(1))
    assert mined == 3
    assert await guild_service.ore_total(db_session, guild.id) == 3


async def test_prayer_and_stat_bonus(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character, gold=5000)
    with pytest.raises(GuildError, match="часовни"):
        await guild_territory_service.pray(db_session, leader, "str")
    cell = await _held_base(db_session, guild, 5, 12)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_CHAPEL, level=1))
    await db_session.flush()
    await guild_service.refresh_perks(db_session, guild)
    cost = await guild_territory_service.pray(db_session, leader, "str")
    assert cost == gc.PRAYER_BASE_COST
    bonus = await guild_territory_service.stat_bonus(db_session, leader, {"str": 200, "agi": 50})
    assert bonus == {"str": 20}


async def test_totem_aura(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    cell = await _held_base(db_session, guild, 5, 12)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_TOTEM, level=9))
    await db_session.flush()
    leader.pos_x, leader.pos_y = 6, 13
    assert await guild_territory_service.totem_double_chance(db_session, leader) == pytest.approx(0.09)
    bonus = await guild_territory_service.stat_bonus(db_session, leader, {"str": 100, "vit": 100})
    assert bonus == {"str": 5, "vit": 5}
    leader.pos_x, leader.pos_y = 8, 12
    assert await guild_territory_service.totem_double_chance(db_session, leader) == 0


async def test_gates(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    a = await _held_base(db_session, guild, 5, 12)
    b = await _held_base(db_session, guild, -5, -12)
    db_session.add_all([
        GuildBuilding(cell_id=a.id, building=gc.B_GATES, level=1),
        GuildBuilding(cell_id=b.id, building=gc.B_GATES, level=1),
    ])
    await db_session.flush()
    leader.pos_x, leader.pos_y = 5, 12
    await guild_territory_service.travel_gates(db_session, leader, b.id)
    assert (leader.pos_x, leader.pos_y) == (-5, -12)
    with pytest.raises(GuildError, match="остыли"):
        await guild_territory_service.travel_gates(db_session, leader, a.id)


async def test_tower_alarm(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    cell = await _held_base(db_session, guild, 5, 12)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_TOWER, level=1))
    await db_session.flush()
    stranger = await make_character(level=40)
    stranger.pos_x, stranger.pos_y = 5, 12
    alarm = await guild_territory_service.on_cell_enter(db_session, stranger)
    assert alarm is not None and alarm.intruder == stranger.name
    assert await guild_territory_service.on_cell_enter(db_session, stranger) is None


# --- Осады ----------------------------------------------------------------------------


async def test_next_window_respects_notice() -> None:
    now = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)  # 13:00 МСК
    start = guild_siege_service.next_window(20, now)
    assert start - now >= timedelta(hours=gc.SIEGE_MIN_NOTICE_HOURS)
    assert start.astimezone(guild_siege_service._TZ).hour == 20


async def test_siege_declare_lock_and_capture(db_session, make_character) -> None:
    attacker, a_leader = await _found(db_session, make_character, "Набег", "НБ")
    defender, d_leader = await _found(db_session, make_character, "Стена", "СТ")
    attacker.level = 10
    cell = await _held_base(db_session, defender, 5, 12)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_CHAPEL, level=2))
    await guild_service.treasury_add(db_session, attacker.id, gold=10**6)
    await guild_service.treasury_add(db_session, defender.id, gold=100_000)
    siege = await guild_siege_service.declare(db_session, a_leader, cell.id)
    assert siege.status == "scheduled"
    with pytest.raises(GuildError):
        await guild_siege_service.declare(db_session, a_leader, cell.id)
    assert await guild_siege_service.lock_at(db_session, 5, 12) is None
    gather_time = guild_service.aware(siege.starts_at) - timedelta(minutes=30)
    assert await guild_siege_service.lock_at(db_session, 5, 12, gather_time) is not None
    gather, start = await guild_siege_service.due(db_session, gather_time)
    assert gather == [siege] and start == []
    outcome = await guild_siege_service.finish(db_session, siege.id, attackers_won=True)
    assert outcome.captured and cell.guild_id == attacker.id
    assert outcome.loot == 10_000
    chapel = await guild_territory_service.building_at(db_session, cell.id, gc.B_CHAPEL)
    assert chapel.level == 1
    assert guild_service.aware(cell.shield_until) > datetime.now(timezone.utc) + timedelta(hours=40)


async def test_siege_repelled_gives_shield(db_session, make_character) -> None:
    attacker, a_leader = await _found(db_session, make_character, "Набег", "НБ")
    defender, _d = await _found(db_session, make_character, "Стена", "СТ")
    attacker.level = 10
    cell = await _held_base(db_session, defender, 5, 12)
    await guild_service.treasury_add(db_session, attacker.id, gold=10**6)
    siege = await guild_siege_service.declare(db_session, a_leader, cell.id)
    await guild_siege_service.finish(db_session, siege.id, attackers_won=False)
    assert siege.status == "repelled" and cell.guild_id == defender.id
    with pytest.raises(GuildError, match="щитом"):
        await guild_siege_service.declare(db_session, a_leader, cell.id)


async def test_garrison_scales_with_barracks(db_session, make_character) -> None:
    attacker, a_leader = await _found(db_session, make_character, "Набег", "НБ")
    defender, _d = await _found(db_session, make_character, "Стена", "СТ")
    cell = await _held_base(db_session, defender, 5, 12)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_BARRACKS, level=6))
    await db_session.flush()
    siege = GuildSiege(
        attacker_guild_id=attacker.id, defender_guild_id=defender.id, cell_id=cell.id, x=5, y=12,
        declared_at=datetime.now(timezone.utc), starts_at=datetime.now(timezone.utc),
    )
    db_session.add(siege)
    await db_session.flush()
    guards = await guild_siege_service.garrison(db_session, siege, -1000)
    assert len(guards) == gc.garrison_size(6) == 3
    assert all(g.side == 1 and g.kind == "mob" for g in guards)


# --- Древо ------------------------------------------------------------------------------


async def test_tree_structure() -> None:
    nodes = guild_tree.build()
    for branch in guild_tree.BRANCHES:
        kinds = [n.kind for n in nodes.values() if n.branch == branch]
        assert kinds.count("small") >= 50 and kinds.count("notable") == 10 and kinds.count("keystone") == 3
    for node in nodes.values():
        for link in node.links:
            assert node.id in nodes[link].links


async def test_tree_allocate_needs_adjacency_points_and_gold(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    with pytest.raises(GuildError, match="очков"):
        await guild_tree_service.allocate(db_session, leader, "kin:1:0")
    guild.level = 5
    with pytest.raises(GuildError, match="рядом"):
        await guild_tree_service.allocate(db_session, leader, "kin:1:5")
    with pytest.raises(GuildError, match="не хватает"):
        await guild_tree_service.allocate(db_session, leader, "kin:1:0")
    await guild_service.treasury_add(db_session, guild.id, gold=10**6)
    node = await guild_tree_service.allocate(db_session, leader, "kin:1:0")
    assert node.effects == {"stat_pct": 0.05}
    assert leader.guild_perks["stat_pct"] == 0.05
    await guild_tree_service.allocate(db_session, leader, "kin:1:1")
    assert guild_service.tree_points_available(guild) == 2


async def test_tree_reset(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    guild.tree_nodes = ["war:0:0"]
    await wallet_service.deposit(db_session, leader.id, "donate", gc.TREE_RESET_GEMS)
    await guild_tree_service.reset(db_session, leader)
    assert guild.tree_nodes == []


# --- Сезоны -------------------------------------------------------------------------------


async def test_season_close(db_session, make_character) -> None:
    from datetime import date

    guild, leader = await _found(db_session, make_character)
    await _held_base(db_session, guild, 5, 12)
    await guild_season_service.snapshot(db_session, date(2026, 9, 30))
    guild.fame_month = 1000
    first = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    result = await guild_season_service.close_if_due(db_session, first)
    assert result.winner.id == guild.id and result.points == 1 + 10
    assert guild_season_service.has_crown(guild)
    assert guild.fame_month == 0
    assert await guild_season_service.close_if_due(db_session, first) is None


# --- Страж цитадели ----------------------------------------------------------------------------


async def test_guild_boss(db_session, make_character) -> None:
    guild, leader = await _found(db_session, make_character)
    with pytest.raises(GuildError, match="цитадели"):
        await guild_boss_service.summon(db_session, leader)
    citadel = await _held_base(db_session, guild, 5, 12, tier=gc.BASE_CITADEL)
    await _ore(db_session, guild.id, gc.BOSS_SUMMON_ORE[0], gc.BOSS_SUMMON_ORE[1])
    await guild_service.treasury_add(db_session, guild.id, gold=gc.BOSS_SUMMON_GOLD)
    boss = await guild_boss_service.summon(db_session, leader)
    assert boss.hp == gc.BOSS_MIN_HP
    leader.pos_x, leader.pos_y = citadel.x, citadel.y
    check = await guild_boss_service.start_attempt(db_session, leader, boss.id)
    assert check.ok
    again = await guild_boss_service.start_attempt(db_session, leader, boss.id)
    assert not again.ok
    damage = await guild_boss_service.apply_damage(db_session, boss.id, leader.id, 10**9)
    assert damage.killed_now
    result = await guild_boss_service.distribute(db_session, boss)
    assert result.share == 1.0 and result.granted[0].gold == gc.BOSS_PERSONAL_GOLD
    await db_session.refresh(guild)
    assert guild.treasury_gold == gc.BOSS_TREASURY_GOLD


async def test_members_listing(db_session, make_character) -> None:
    guild, _leader = await _found(db_session, make_character)
    await _add(db_session, make_character, guild)
    rows = await guild_service.members(db_session, guild.id)
    assert len(rows) == 2
    assert await db_session.scalar(select(Guild).where(Guild.id == guild.id)) is not None
    assert len((await db_session.scalars(select(GuildMember))).all()) == 2


# --- API мини-аппа -------------------------------------------------------------------------


async def test_api_state_and_actions(db_session, make_character) -> None:
    from bot import miniapp_guild_api as api

    loner = await make_character(level=25, donate=gc.FOUND_COST_GEMS)
    loner.pos_x, loner.pos_y = 5, 12
    state = await api._state(db_session, loner)
    assert state["in_guild"] is False and state["found_cost"] == gc.FOUND_COST_GEMS
    await api._act(db_session, loner, 1, {"action": "create", "name": "Тест Гильдия", "tag": "TG"})
    guild = await guild_service.guild_of(db_session, loner)
    cell = await _held_base(db_session, guild, 5, 12, tier=gc.BASE_CITADEL)
    db_session.add(GuildBuilding(cell_id=cell.id, building=gc.B_GATES, level=1))
    await db_session.flush()
    state = await api._state(db_session, loner)
    assert state["in_guild"] and state["me"]["rank"] == gc.RANK_LEADER
    assert state["cells"][0]["here"] and state["boss"]["has_citadel"]
    assert any(b["building"] == gc.B_SHAFT for b in state["cells"][0]["buildings"]) is False
    with pytest.raises(GuildError):
        await api._act(db_session, loner, 1, {"action": "nope"})
    with pytest.raises(GuildError):
        await api._act(db_session, loner, 1, {"action": "deposit", "currency": "gold", "amount": "x"})
    tree = guild_tree_service.payload(guild)
    assert len(tree["nodes"]) == len(guild_tree.build())
