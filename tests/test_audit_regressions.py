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
    from bot.handlers import rest as rest_handlers
    monkeypatch.setattr(rest_handlers, "get_session_factory", lambda: Context)
    from bot.handlers import explore as explore_handlers
    monkeypatch.setattr(explore_handlers, "get_session_factory", lambda: Context)
    monkeypatch.setattr(world.onboarding_svc, "get_character", get_character)
    handler = raid_combat if mode == "raid" else group_combat
    name = "has_active_battle" if mode == "raid" else "has_active_group_battle"
    monkeypatch.setattr(handler, name, lambda peer: True)
    replies = []
    async def answer(*args, **kwargs): replies.append(args)
    message = SimpleNamespace(peer_id=777, from_id=777, text="↑", answer=answer)
    for action in (world.move, world.explore, rest_handlers.rest):
        await action(message)
    assert len(replies) == 3
    assert player.travel_arrives_at is None
    from bot import explore_rest

    assert not explore_rest.busy(777)


async def test_pvp_attack_interrupts_group_pve_without_result(monkeypatch, db_session, make_character):
    """2026-10-15: нападение на участника группового боя с мобами обрывает
    бой для всей группы без итога; HP сохраняется, остальным - весть."""
    from bot.handlers import group_combat as gc

    a = await make_character(region="ridge")
    b = await make_character(region="ridge")
    for c in (a, b):
        c.pos_x, c.pos_y = 5, 20
    battle_id = -9999
    battle = gc.GroupBattle(group_id=4242, participants={
        a.id: gc.Participant(a.id, 501, a.name, a.base_class, None),
        b.id: gc.Participant(b.id, 502, b.name, b.base_class, None),
    }, mob_ids={1})
    gc._battles[battle_id] = battle
    gc._peer_battle.update({501: battle_id, 502: battle_id})
    gc._active_group_ids.add(4242)
    aborted = []

    class Engine:
        sessions = {battle_id: SimpleNamespace(combatants={a.id: SimpleNamespace(current_hp=50), b.id: SimpleNamespace(current_hp=40)})}
        def abort_session(self, sid): aborted.append(sid)

    class Context:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *args): pass

    sent = []
    async def send(**kw): sent.append(kw)
    async def summary(*args): pass
    monkeypatch.setattr(gc, "_engine", Engine())
    monkeypatch.setattr(gc, "_bot_api", SimpleNamespace(messages=SimpleNamespace(send=send)))
    monkeypatch.setattr(gc, "get_session_factory", lambda: Context)
    monkeypatch.setattr(gc, "_send_location_summary", summary)
    await gc.interrupt_for_pvp(501)
    assert aborted == [battle_id]
    assert not gc.has_active_group_battle(501) and not gc.has_active_group_battle(502)
    assert not gc.is_group_fighting(4242)
    assert [m["peer_id"] for m in sent] == [502] and "напали" in sent[0]["message"]


async def test_group_victory_raises_fallen_member(monkeypatch, db_session, make_character):
    """2026-10-15: группа победила - павший в бою не умирает, встаёт с 10% HP."""
    from bot.handlers import group_combat as gc
    from services import death_service

    a = await make_character(region="ridge")
    b = await make_character(region="ridge")
    for c in (a, b):
        c.pos_x, c.pos_y = 5, 20
    battle_id = -9998
    battle = gc.GroupBattle(group_id=4343, participants={
        a.id: gc.Participant(a.id, 601, a.name, a.base_class, None),
        b.id: gc.Participant(b.id, 602, b.name, b.base_class, None),
    }, mob_ids={99999})
    battle.last_combatants = {
        a.id: SimpleNamespace(alive=True, current_hp=80, max_hp=100, kind="character", level=a.level),
        b.id: SimpleNamespace(alive=False, current_hp=0, max_hp=100, kind="character", level=b.level),
        99999: SimpleNamespace(alive=False, current_hp=0, max_hp=50, kind="mob", level=1),
    }
    gc._battles[battle_id] = battle

    class Context:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *args): pass

    sent = []
    async def send(**kw): sent.append(kw)
    async def summary(*args): pass
    monkeypatch.setattr(gc, "_bot_api", SimpleNamespace(messages=SimpleNamespace(send=send)))
    monkeypatch.setattr(gc, "get_session_factory", lambda: Context)
    monkeypatch.setattr(gc, "_send_location_summary", summary)
    monkeypatch.setattr(gc.ash_service, "roll_appears", lambda rng: False)
    await gc.on_group_battle_finished(battle_id, SimpleNamespace())
    assert not death_service.is_dead(b)
    assert any(m["peer_id"] == 602 and "подняла тебя" in m["message"] for m in sent)
