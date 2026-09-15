"""Патч 53: лобби рейда (сбор у Монолита) — services/raid_service.py."""

import pytest

from game.economy import raid_config as rc
from services import group_service as gs
from services import raid_service as rs


async def _make_group(db_session, make_character, size: int = 2):
    """Возвращает (group_id, [leader, member2, ...])."""
    leader = await make_character(level=60)
    members = [leader]
    group_id = None
    for _ in range(size - 1):
        member = await make_character(level=60)
        invite = await gs.send_invite(db_session, leader, member)
        result = await gs.accept_invite(db_session, invite.id, member.id)
        group_id = result.group.id
        members.append(member)
    return group_id, members


async def test_solo_touch_creates_lobby_ready_immediately(db_session, make_character) -> None:
    player = await make_character(level=60)
    snapshot = await rs.touch_monolith(db_session, player, rc.RAID_PUPPET_THEATRE_ID, group_id=None)
    assert snapshot.group_id is None
    assert snapshot.denominator == 1
    assert rs.is_ready_to_start(snapshot) is True


async def test_cannot_touch_twice(db_session, make_character) -> None:
    player = await make_character(level=60)
    await rs.touch_monolith(db_session, player, rc.RAID_PUPPET_THEATRE_ID, group_id=None)
    with pytest.raises(rs.RaidError):
        await rs.touch_monolith(db_session, player, rc.RAID_PUPPET_THEATRE_ID, group_id=None)


async def test_group_lobby_denominator_is_group_size(db_session, make_character) -> None:
    group_id, (leader, member2, member3) = await _make_group(db_session, make_character, size=3)
    snapshot = await rs.get_snapshot(
        db_session,
        (await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)).id,
    )
    assert snapshot.denominator == 3
    assert rs.is_ready_to_start(snapshot) is False


async def test_group_lobby_ready_when_all_touched(db_session, make_character) -> None:
    group_id, (leader, member2) = await _make_group(db_session, make_character, size=2)
    snap1 = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    assert rs.is_ready_to_start(snap1) is False
    snap2 = await rs.touch_monolith(db_session, member2, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    assert snap2.id == snap1.id  # присоединился к ТОМУ ЖЕ лобби
    assert rs.is_ready_to_start(snap2) is True


async def test_second_member_different_raid_rejected(db_session, make_character) -> None:
    group_id, (leader, member2) = await _make_group(db_session, make_character, size=2)
    await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    with pytest.raises(rs.RaidError):
        await rs.touch_monolith(db_session, member2, "some_other_raid", group_id=group_id)


async def test_cancel_readiness_keeps_membership_but_not_ready(db_session, make_character) -> None:
    group_id, (leader, member2) = await _make_group(db_session, make_character, size=2)
    await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    snap = await rs.touch_monolith(db_session, member2, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    assert rs.is_ready_to_start(snap) is True

    snap_after_cancel = await rs.cancel_readiness(db_session, member2.id)
    assert len(snap_after_cancel.members) == 2  # остался в лобби
    assert rs.is_ready_to_start(snap_after_cancel) is False
    # Лидер по-прежнему готов, member2 больше нет
    ready_map = {c.id: ready for c, ready in snap_after_cancel.members}
    assert ready_map[leader.id] is True
    assert ready_map[member2.id] is False


async def test_leave_lobby_decreases_denominator(db_session, make_character) -> None:
    group_id, (leader, member2, member3) = await _make_group(db_session, make_character, size=3)
    await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, member2, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    snap = await rs.leave_lobby_if_present(db_session, member2.id)
    assert len(snap.members) == 1
    assert snap.denominator == 3  # знаменатель = размер группы, а не число вошедших в лобби


async def test_leave_lobby_last_member_dissolves_it(db_session, make_character) -> None:
    player = await make_character(level=60)
    await rs.touch_monolith(db_session, player, rc.RAID_PUPPET_THEATRE_ID, group_id=None)
    result = await rs.leave_lobby_if_present(db_session, player.id)
    assert result is None
    assert await rs.get_membership(db_session, player.id) is None


async def test_group_leave_group_removes_raid_lobby_membership(db_session, make_character) -> None:
    """Патч 53: выход из ГРУППЫ (не только с клетки) тоже снимает
    членство в рейд-лобби — интеграция через group_service.leave_group."""
    group_id, (leader, member2) = await _make_group(db_session, make_character, size=2)
    await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, member2, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    await gs.leave_group(db_session, member2.id)
    assert await rs.get_membership(db_session, member2.id) is None
    snapshot = await rs.get_snapshot(db_session, (await rs.get_membership(db_session, leader.id)).lobby_id)
    assert len(snapshot.members) == 1


async def test_consume_key_and_start_requires_key(db_session, make_character) -> None:
    player = await make_character(level=60)
    assert player.raid_keys == 0
    ok = await rs.consume_key_and_start(db_session, player)
    assert ok is False
    assert player.raid_keys == 0


async def test_consume_key_and_start_burns_key_on_success(db_session, make_character) -> None:
    player = await make_character(level=60)
    player.raid_keys = 2
    ok = await rs.consume_key_and_start(db_session, player)
    assert ok is True
    assert player.raid_keys == 1


async def test_dissolve_lobby_removes_everything(db_session, make_character) -> None:
    group_id, (leader, member2) = await _make_group(db_session, make_character, size=2)
    snap = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, member2, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.dissolve_lobby(db_session, snap.id)
    assert await rs.get_membership(db_session, leader.id) is None
    assert await rs.get_membership(db_session, member2.id) is None
    assert await rs.get_snapshot(db_session, snap.id) is None
