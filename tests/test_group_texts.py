"""Отображение группы в чате (патч 51, ч.2): bot/group_texts.py."""

from bot import group_texts
from services import group_service as gs


async def test_group_summary_block_none_when_not_in_group(db_session, make_character) -> None:
    solo = await make_character()
    assert await group_texts.group_summary_block(db_session, solo.id) is None


async def test_group_summary_block_marks_leader_and_lists_all(db_session, make_character) -> None:
    leader = await make_character(level=10, region="ridge")
    member = await make_character(level=12, region="ridge")
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)
    for c in (leader, member):
        c.pos_x, c.pos_y = 5, -5

    block = await group_texts.group_summary_block(db_session, leader.id)
    assert block.startswith("👥 ГРУППА")
    assert f"👑 {leader.name}" in block
    assert f"{member.name} ·" in block
    assert f"👑 {member.name}" not in block  # участник — не лидер, короны нет
    assert "(5; -5)" in block
    assert "10 ур." in block and "12 ур." in block


async def test_group_summary_block_same_for_any_member(db_session, make_character) -> None:
    leader = await make_character(level=10)
    member = await make_character(level=10)
    invite = await gs.send_invite(db_session, leader, member)
    await gs.accept_invite(db_session, invite.id, member.id)

    from_leader = await group_texts.group_summary_block(db_session, leader.id)
    from_member = await group_texts.group_summary_block(db_session, member.id)
    assert from_leader == from_member


def test_level_gap_kick_line_mentions_name() -> None:
    kick = gs.LevelGapKick(
        kicked_character_id=1, kicked_name="Гостус", dissolved=False,
        new_leader_character_id=None, remaining_member_character_ids=[2],
    )
    line = group_texts.level_gap_kick_line(kick)
    assert "Гостус" in line


def test_level_gap_kick_self_line_is_stable_text() -> None:
    assert "исключён" in group_texts.level_gap_kick_self_line()
