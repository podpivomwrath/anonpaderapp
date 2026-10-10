"""Разломы: появление, очередь у входа, исчезновение и механики этапов."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.combat import rift as rift_combat
from game.combat.resolver import TickResult
from game.combat.session import CombatMode, CombatSessionState, Stats, build_combatant
from game.economy import rift_config as rc
from game.world import grid
from services import rift_service

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


async def _rift(db, ring=2, kind="ash_crypt", now=NOW):
    return await rift_service.spawn(db, random.Random(3), now, ring=ring, kind=kind)


async def _at(character, rift, level):
    character.pos_x, character.pos_y, character.level = rift.x, rift.y, level
    return character


# --- Появление ---------------------------------------------------------------------


async def test_spawn_lands_in_ring_on_pvp_cell(db_session) -> None:
    for ring in rc.BANDS:
        rift = await _rift(db_session, ring=ring)
        assert grid.ring_tier(rift.x, rift.y) == ring
        assert not grid.pvp_forbidden(rift.x, rift.y)
        assert rift.expires_at - rift.spawned_at == timedelta(minutes=rc.LIFETIME_MINUTES)


async def test_explorations_fill_meter_and_cap_active(db_session) -> None:
    rng = random.Random(1)
    spawned = []
    for _ in range(rc.EXPLORATIONS_PER_SPAWN * (rc.MAX_ACTIVE + 2)):
        rift = await rift_service.record_exploration(db_session, rng, NOW)
        if rift is not None:
            spawned.append(rift)
    assert len(spawned) == rc.MAX_ACTIVE
    cells = {(r.x, r.y) for r in spawned}
    assert len(cells) == rc.MAX_ACTIVE  # не друг на друге


# --- Вход ----------------------------------------------------------------------------


async def test_entry_rules(db_session, make_character) -> None:
    rift = await _rift(db_session, ring=2, kind="ash_crypt")  # 16-30, до 3
    a = await _at(await make_character(), rift, 20)
    young = await _at(await make_character(), rift, 15)
    assert "Не по уровню" in rift_service.entry_refusal(rift, [a, young], NOW)
    old = await _at(await make_character(), rift, 31)
    assert "Не по уровню" in rift_service.entry_refusal(rift, [old], NOW)
    four = [await _at(await make_character(), rift, 20) for _ in range(4)]
    assert "не больше 3" in rift_service.entry_refusal(rift, four, NOW)
    away = await make_character(level=20)
    assert "Нет на месте" in rift_service.entry_refusal(rift, [a, away], NOW)
    assert rift_service.entry_refusal(rift, [a], NOW) is None  # соло можно


async def test_one_group_at_a_time_and_cancel(db_session, make_character) -> None:
    rift = await _rift(db_session)
    first = await _at(await make_character(), rift, 20)
    second = await _at(await make_character(), rift, 20)
    await rift_service.begin_wait(db_session, rift.id, [first], None, NOW)
    assert rift.state == rift_service.WAITING
    with pytest.raises(rift_service.RiftError, match="занят"):
        await rift_service.begin_wait(db_session, rift.id, [second], None, NOW)
    assert await rift_service.cancel_wait(db_session, rift.id, NOW) == [first.id]
    assert rift.state == rift_service.FREE
    await rift_service.begin_wait(db_session, rift.id, [second], None, NOW)


async def test_wait_due_after_a_minute_and_drop_members(db_session, make_character) -> None:
    rift = await _rift(db_session)
    a = await _at(await make_character(), rift, 20)
    b = await _at(await make_character(), rift, 25)
    await rift_service.begin_wait(db_session, rift.id, [a, b], None, NOW)
    assert await rift_service.due_waits(db_session, NOW + timedelta(seconds=59)) == []
    assert await rift_service.due_waits(db_session, NOW + timedelta(seconds=rc.ENTRY_WAIT_SECONDS)) == [rift.id]
    assert (await rift_service.drop_members(db_session, rift.id, [a.id], NOW)).members == [b.id]
    assert await rift_service.drop_members(db_session, rift.id, [b.id], NOW) is None
    assert rift.state == rift_service.FREE


async def test_run_level_follows_eldest_within_band(db_session, make_character) -> None:
    rift = await _rift(db_session, ring=2)
    a = await _at(await make_character(), rift, 18)
    b = await _at(await make_character(), rift, 27)
    assert await rift_service.start_run(db_session, rift, [a, b]) == 27
    assert rift.state == rift_service.RUNNING


# --- Исчезновение --------------------------------------------------------------------


async def test_expired_rift_waits_for_group_then_vanishes(db_session, make_character) -> None:
    rift = await _rift(db_session)
    a = await _at(await make_character(), rift, 20)
    await rift_service.begin_wait(db_session, rift.id, [a], None, NOW)
    await rift_service.start_run(db_session, rift, [a])
    late = NOW + timedelta(minutes=rc.LIFETIME_MINUTES + 5)
    assert await rift_service.expire_due(db_session, late) == 0
    assert rift in await rift_service.active_rifts(db_session, late)  # внутри группа
    await rift_service.finish_run(db_session, rift.id, cleared=False, now=late)
    assert rift.status == rift_service.EXPIRED  # время вышло - сразу исчезает


async def test_cleared_rift_closes_and_failed_one_is_free_again(db_session, make_character) -> None:
    rift = await _rift(db_session)
    a = await _at(await make_character(), rift, 20)
    await rift_service.start_run(db_session, rift, [a])
    await rift_service.finish_run(db_session, rift.id, cleared=False, now=NOW)
    assert (rift.status, rift.state) == (rift_service.ACTIVE, rift_service.FREE)
    await rift_service.start_run(db_session, rift, [a])
    await rift_service.finish_run(db_session, rift.id, cleared=True, now=NOW)
    assert rift.status == rift_service.CLEARED


async def test_recover_frees_held_rifts(db_session, make_character) -> None:
    rift = await _rift(db_session)
    a = await _at(await make_character(), rift, 20)
    await rift_service.begin_wait(db_session, rift.id, [a], None, NOW)
    assert await rift_service.recover(db_session, NOW) == [a.id]
    assert rift.state == rift_service.FREE


# --- Этапы ---------------------------------------------------------------------------


def _session(players: int = 3) -> CombatSessionState:
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for i in range(players):
        session.add(build_combatant(
            id=i + 1, side=0, kind="character", name=f"P{i}", level=30,
            stats=Stats(strength=60, agility=20, intellect=10, vitality=40, will=10), primary_stat="str",
        ))
    return session


@pytest.mark.parametrize("kind", sorted(rc.RIFT_TYPES))
def test_every_stage_builds(kind) -> None:
    for stage_no in range(1, rift_combat.stage_count(kind) + 1):
        session = _session()
        stage = rift_combat.build_stage(kind, stage_no, 1000, 30, 2)
        stage.setup(session)
        assert stage.reward_ids and all(session.combatants[i].alive for i in stage.reward_ids)
    assert stage.is_boss  # последний - босс
    assert rc.RIFT_TYPES[kind].legendaries == (2 if rc.RIFT_TYPES[kind].max_size >= 5 else 1)


def test_shard_explodes_if_not_killed() -> None:
    session = _session()
    stage = rift_combat.build_stage("shard_nest", 2, 1000, 30, 2)
    stage.setup(session)
    rng = random.Random(1)
    lines = []
    for _ in range(rc.SHARD_EVERY + rc.SHARD_FUSE):
        lines += stage.after_tick(session, TickResult(), rng).lines
    assert any("взрывается" in line for line in lines)
    hurt = [c for c in session.combatants.values() if c.kind == "character" and c.current_hp < c.max_hp]
    assert len(hurt) == 3


def test_keeper_turns_to_stone_and_back() -> None:
    session = _session()
    stage = rift_combat.build_stage("ash_crypt", 2, 1000, 30, 2)
    stage.setup(session)
    boss = stage.boss(session)
    rng = random.Random(1)
    for _ in range(rc.STONE_EVERY):
        stage.after_tick(session, TickResult(), rng)
    assert boss.buff_modifiers["incoming_damage_reduction"] == rc.STONE_REDUCTION
    for _ in range(rc.STONE_TICKS):
        stage.after_tick(session, TickResult(), rng)
    assert boss.buff_modifiers["incoming_damage_reduction"] == 0.0


def test_double_splits_at_half() -> None:
    session = _session()
    stage = rift_combat.build_stage("mirror_rift", 2, 1000, 30, 2)
    stage.setup(session)
    boss = stage.boss(session)
    boss.current_hp = int(boss.max_hp * 0.4)
    before = boss.current_hp
    stage.after_tick(session, TickResult(), random.Random(1))
    assert len(stage.reward_ids) == 2
    twin = session.combatants[max(stage.reward_ids)]
    assert boss.current_hp + twin.current_hp == before


def test_deep_one_enrages_and_drags() -> None:
    session = _session()
    stage = rift_combat.build_stage("blood_pool", 3, 1000, 30, 2)
    stage.setup(session)
    frozen = []
    for _ in range(rc.DRAG_EVERY):
        frozen += stage.after_tick(session, TickResult(), random.Random(1)).frozen
    assert stage.boss(session).buff_modifiers["damage_bonus"] > 0
    assert len(frozen) == 1
