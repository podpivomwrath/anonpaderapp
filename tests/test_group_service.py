"""Группы (патч 51, ч.2): приглашения/лидерство/лимиты — services/group_service.py."""

from datetime import datetime, timedelta, timezone

import pytest

from game.economy import group_config as gc
from services import group_service as gs


async def test_send_invite_creates_pending_invite_without_group(db_session, make_character) -> None:
    leader = await make_character(level=10)
    target = await make_character(level=12)
    invite = await gs.send_invite(db_session, leader, target)
    assert invite.status == "pending"
    assert invite.group_id is None
    assert invite.from_character_id == leader.id
    assert invite.to_character_id == target.id


async def test_cannot_invite_self(db_session, make_character) -> None:
    leader = await make_character()
    with pytest.raises(gs.GroupError):
        await gs.send_invite(db_session, leader, leader)


async def test_accept_invite_creates_group_with_leader_and_member(db_session, make_character) -> None:
    leader = await make_character(level=10)
    target = await make_character(level=12)
    invite = await gs.send_invite(db_session, leader, target)
    result = await gs.accept_invite(db_session, invite.id, target.id)
    assert result.newly_created is True
    assert result.group.leader_character_id == leader.id
    assert {m.id for m in result.group.members} == {leader.id, target.id}


async def test_decline_invite_marks_declined(db_session, make_character) -> None:
    leader = await make_character()
    target = await make_character()
    invite = await gs.send_invite(db_session, leader, target)
    await gs.decline_invite(db_session, invite.id, target.id)
    with pytest.raises(gs.GroupError):
        await gs.accept_invite(db_session, invite.id, target.id)


async def test_accept_invite_wrong_character_rejected(db_session, make_character) -> None:
    leader = await make_character()
    target = await make_character()
    stranger = await make_character()
    invite = await gs.send_invite(db_session, leader, target)
    with pytest.raises(gs.GroupError):
        await gs.accept_invite(db_session, invite.id, stranger.id)


async def test_invite_expires_after_ttl(db_session, make_character) -> None:
    leader = await make_character()
    target = await make_character()
    invite = await gs.send_invite(db_session, leader, target)
    invite.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()
    with pytest.raises(gs.GroupError, match="истекл"):
        await gs.accept_invite(db_session, invite.id, target.id)


async def test_only_one_active_invite_per_target(db_session, make_character) -> None:
    leader = await make_character()
    other_inviter = await make_character()
    target = await make_character()
    # Ссылка удерживается явно — без неё SQLAlchemy может собрать объект по
    # слабой ссылке и перечитать expires_at из SQLite наивным (тестовый
    # артефакт; Postgres TIMESTAMPTZ в проде всегда возвращает aware).
    first_invite = await gs.send_invite(db_session, leader, target)
    with pytest.raises(gs.GroupError, match="уже рассматривает"):
        await gs.send_invite(db_session, other_inviter, target)
    assert first_invite.status == "pending"


async def test_second_invite_allowed_after_first_declined(db_session, make_character) -> None:
    leader = await make_character()
    target = await make_character()
    invite = await gs.send_invite(db_session, leader, target)
    await gs.decline_invite(db_session, invite.id, target.id)
    second = await gs.send_invite(db_session, leader, target)
    assert second.id != invite.id


async def test_cannot_invite_already_grouped_player(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    other_leader = await make_character(level=10)
    with pytest.raises(gs.GroupError, match="уже состоит в группе"):
        await gs.send_invite(db_session, other_leader, member)


async def test_only_leader_can_invite(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    third = await make_character(level=10)
    with pytest.raises(gs.GroupError, match="только лидер"):
        await gs.send_invite(db_session, member, third)


async def test_level_gap_blocks_invite(db_session, make_character) -> None:
    leader = await make_character(level=5)
    too_high = await make_character(level=20)
    with pytest.raises(gs.GroupError, match="Разрыв уровней"):
        await gs.send_invite(db_session, leader, too_high)


async def test_level_gap_exactly_at_limit_allowed(db_session, make_character) -> None:
    leader = await make_character(level=10)
    target = await make_character(level=10 + gc.GROUP_MAX_LEVEL_GAP)
    invite = await gs.send_invite(db_session, leader, target)
    assert invite.status == "pending"


async def test_group_size_cap(db_session, make_character) -> None:
    leader = await make_character(level=10)
    members = []
    for _ in range(gc.GROUP_MAX_SIZE - 1):
        m = await make_character(level=10)
        inv = await gs.send_invite(db_session, leader, m)
        await gs.accept_invite(db_session, inv.id, m.id)
        members.append(m)
    overflow = await make_character(level=10)
    with pytest.raises(gs.GroupError, match="полная"):
        await gs.send_invite(db_session, leader, overflow)


# --- Выход / лидерство / роспуск ---


async def test_leave_transfers_leadership_to_next_by_join_order(db_session, make_character) -> None:
    leader = await make_character(level=10)
    second = await make_character(level=10)
    third = await make_character(level=10)
    inv1 = await gs.send_invite(db_session, leader, second)
    await gs.accept_invite(db_session, inv1.id, second.id)
    inv2 = await gs.send_invite(db_session, leader, third)
    await gs.accept_invite(db_session, inv2.id, third.id)

    result = await gs.leave_group(db_session, leader.id)
    assert result.dissolved is False
    assert result.new_leader_character_id == second.id

    snapshot = await gs.get_group_snapshot(db_session, second.id)
    assert snapshot.leader_character_id == second.id
    assert {m.id for m in snapshot.members} == {second.id, third.id}


async def test_leave_dissolves_group_when_last_member_leaves(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    await gs.leave_group(db_session, leader.id)
    result = await gs.leave_group(db_session, member.id)
    assert result.dissolved is True
    assert await gs.get_group_snapshot(db_session, member.id) is None


async def test_leave_not_in_group_raises(db_session, make_character) -> None:
    solo = await make_character()
    with pytest.raises(gs.GroupError):
        await gs.leave_group(db_session, solo.id)


async def test_kick_member_only_by_leader(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    with pytest.raises(gs.GroupError, match="только лидер"):
        await gs.kick_member(db_session, member, leader.id)

    result = await gs.kick_member(db_session, leader, member.id)
    assert result.dissolved is False
    assert await gs.get_group_snapshot(db_session, member.id) is None


async def test_kick_self_rejected(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)
    with pytest.raises(gs.GroupError, match="исключить самого себя"):
        await gs.kick_member(db_session, leader, leader.id)


# --- Разрыв уровней при левелапе ---


async def test_enforce_level_gap_kicks_leveled_up_member(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    member.level = 25  # разрыв теперь 15 > 10
    kick = await gs.enforce_level_gap(db_session, member)
    assert kick is not None
    assert kick.kicked_character_id == member.id
    assert kick.dissolved is False
    assert await gs.get_group_snapshot(db_session, member.id) is None
    # лидер остаётся лидером — исключили НЕ его
    snapshot = await gs.get_group_snapshot(db_session, leader.id)
    assert snapshot.leader_character_id == leader.id


async def test_enforce_level_gap_kicks_leader_and_transfers(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    leader.level = 25
    kick = await gs.enforce_level_gap(db_session, leader)
    assert kick is not None
    assert kick.kicked_character_id == leader.id
    assert kick.new_leader_character_id == member.id
    snapshot = await gs.get_group_snapshot(db_session, member.id)
    assert snapshot.leader_character_id == member.id


async def test_enforce_level_gap_noop_within_limit(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    member.level = 15  # разрыв 5, в пределах нормы
    assert await gs.enforce_level_gap(db_session, member) is None


async def test_enforce_level_gap_noop_when_not_in_group(db_session, make_character) -> None:
    solo = await make_character(level=50)
    assert await gs.enforce_level_gap(db_session, solo) is None
