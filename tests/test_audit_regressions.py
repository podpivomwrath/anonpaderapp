import asyncio
from types import SimpleNamespace

import pytest

from bot.activity import ActivityBusy, transition
from game.combat.session import CombatMode
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from models import CharacterStats, RaidRun
from services import raid_service as rs, group_service as gs, stat_alloc_service as sas
from tests.conftest import combatant, NoCritRng
from tests.test_tick_engine import make_state, attack
from tests.test_raid_service import _make_group


async def test_two_resolvers_only_advance_one_turn():
    entered, release = asyncio.Event(), asyncio.Event()
    ticks = []
    async def on_tick(sid, tick, result):
        ticks.append(tick)
        entered.set()
        await release.wait()
    engine = TickEngine(InMemoryActionStore(), rng=NoCritRng(), on_tick_resolved=on_tick)
    state = make_state(CombatMode.PVE, combatant(1, 0, vitality=200), combatant(2, 1, kind="mob", vitality=200))
    engine.start_session(state)
    first = asyncio.create_task(engine.declare_action(1, 1, attack(2)))
    await entered.wait()
    timeout = asyncio.create_task(engine._resolve(1, 1, state))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, timeout)
    assert ticks == [1]
    assert state.tick_number == 2


async def test_stale_timeout_cannot_resolve_new_raid_stage():
    engine = TickEngine(InMemoryActionStore(), rng=NoCritRng())
    old = make_state(CombatMode.PVE, combatant(1, 0), combatant(2, 1, kind="mob"))
    new = make_state(CombatMode.PVE, combatant(1, 0), combatant(2, 1, kind="mob"))
    engine.start_session(old)
    engine.abort_session(1)
    engine.start_session(new)
    await engine._resolve(1, 1, old)
    assert new.tick_number == 1


async def test_callback_abort_does_not_reopen_tick():
    engine = TickEngine(InMemoryActionStore(), rng=NoCritRng())
    async def abort(sid, tick, result):
        engine.abort_session(sid)
    engine.on_tick_resolved = abort
    state = make_state(CombatMode.PVE, combatant(1, 0), combatant(2, 1, kind="mob", vitality=200))
    engine.start_session(state)
    await engine.declare_action(1, 1, attack(2))
    assert state.tick_number == 1
    assert not engine.sessions


async def test_ready_can_be_restored(db_session, make_character):
    player = await make_character()
    original = await rs.touch_monolith(db_session, player, "puppet_theatre", None)
    await rs.cancel_readiness(db_session, player.id)
    restored = await rs.touch_monolith(db_session, player, "puppet_theatre", None)
    assert restored.id == original.id
    assert rs.is_ready_to_start(restored)


async def test_lobby_transfers_leader_on_group_exit(db_session, make_character):
    gid, (a, b, c) = await _make_group(db_session, make_character, 3)
    await rs.touch_monolith(db_session, a, "puppet_theatre", gid)
    await rs.touch_monolith(db_session, b, "puppet_theatre", gid)
    await gs.leave_group(db_session, a.id)
    snapshot = await rs.touch_monolith(db_session, c, "puppet_theatre", gid)
    assert snapshot.leader_character_id == b.id
    assert rs.is_ready_to_start(snapshot)


async def test_refund_survives_restart_and_is_once(db_session, make_character):
    player = await make_character()
    player.raid_keys = 2
    snap = await rs.touch_monolith(db_session, player, "puppet_theatre", None)
    assert await rs.consume_key_and_start(db_session, player)
    run = await rs.record_run(db_session, snap)
    await rs.dissolve_lobby(db_session, snap.id)
    await db_session.commit()
    await rs.recover_interrupted(db_session)
    await db_session.commit()
    await rs.recover_interrupted(db_session)
    await db_session.refresh(player)
    assert player.raid_keys == 2
    assert (await db_session.get(RaidRun, run.id)).status == "interrupted"


async def test_finished_raid_not_refunded(db_session, make_character):
    player = await make_character()
    player.raid_keys = 1
    snap = await rs.touch_monolith(db_session, player, "puppet_theatre", None)
    await rs.consume_key_and_start(db_session, player)
    run = await rs.record_run(db_session, snap)
    await rs.finish_run(db_session, run.id)
    await db_session.commit()
    assert await rs.recover_interrupted(db_session) == []
    await db_session.refresh(player)
    assert player.raid_keys == 0


async def test_atomic_stats_reject_stale_budget(db_session, make_character):
    player = await make_character()
    stats = await db_session.get(CharacterStats, player.id)
    stats.unspent_points = 3
    await db_session.flush()
    await sas.allocate(db_session, stats, {"str": 3})
    with pytest.raises(sas.NotEnoughPoints):
        await sas.allocate(db_session, stats, {"agi": 3})
    assert stats.strength == 18 and stats.agility == 15


async def test_activity_reservations_conflict_and_release():
    entered, release = asyncio.Event(), asyncio.Event()
    async def reserve():
        with transition([123]):
            with transition([123, 124]):
                entered.set()
                await release.wait()
    task = asyncio.create_task(reserve())
    await entered.wait()
    with pytest.raises(ActivityBusy):
        with transition([123]):
            pass
    release.set()
    await task
    with transition([123, 124]):
        pass


@pytest.mark.parametrize("mode", ["raid", "group"])
async def test_world_actions_blocked_in_party_battle(monkeypatch, db_session, make_character, mode):
    from bot.handlers import world, raid_combat, group_combat
    player = await make_character(region="ridge")
    player.pos_x = player.pos_y = 0
    async def get_character(*args): return player
    class Context:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *args): pass
    monkeypatch.setattr(world, "get_session_factory", lambda: Context)
    monkeypatch.setattr(world.onboarding_svc, "get_character", get_character)
    handler = raid_combat if mode == "raid" else group_combat
    name = "has_active_battle" if mode == "raid" else "has_active_group_battle"
    monkeypatch.setattr(handler, name, lambda peer: True)
    replies = []
    async def answer(*args, **kwargs): replies.append(args)
    message = SimpleNamespace(peer_id=777, from_id=777, text="↑", answer=answer)
    for action in (world.move, world.explore, world.rest):
        await action(message)
    assert len(replies) == 3
    assert player.travel_arrives_at is None
    assert 777 not in world._resting and 777 not in world._exploring
