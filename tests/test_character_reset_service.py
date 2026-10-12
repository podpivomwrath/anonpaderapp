"""services/character_reset_service.py: обнуление персонажа игроку «начать заново»."""

import pytest
from sqlalchemy import select

from game.economy import guild_config as gc
from models import AdminAction, Character, CharacterFish, Guild, GuildMember, User, Wallet
from services import character_reset_service as crs

ADMIN_VK_ID = 106468413


@pytest.mark.asyncio
async def test_reset_deletes_character_keeps_user_and_logs_it(db_session, make_character) -> None:
    character = await make_character(level=7, farm=300, donate=40)
    db_session.add(CharacterFish(
        character_id=character.id, fish_id="monolith_catfish", grade="common", total_grams=900,
    ))
    await db_session.flush()
    cid, user_id, name = character.id, character.user_id, character.name

    info = await crs.reset_character(db_session, ADMIN_VK_ID, cid)
    await db_session.commit()

    assert info["name"] == name and info["donate_currency"] == 40
    assert await db_session.get(Character, cid) is None
    assert await db_session.get(Wallet, cid) is None
    assert await db_session.get(User, user_id) is not None
    action = await db_session.scalar(select(AdminAction).where(AdminAction.action_type == "reset_character"))
    assert action is not None
    assert action.old_value["name"] == name and action.old_value["donate_currency"] == 40
    assert action.target_character_id is None  # журнал пережил удаление


@pytest.mark.asyncio
async def test_reset_refused_for_guild_leader(db_session, make_character) -> None:
    leader = await make_character()
    guild = Guild(name="Гильдия", tag="ГИЛ")
    db_session.add(guild)
    await db_session.flush()
    db_session.add(GuildMember(guild_id=guild.id, character_id=leader.id, rank=gc.RANK_LEADER))
    await db_session.flush()

    with pytest.raises(crs.ResetBlocked) as excinfo:
        await crs.reset_character(db_session, ADMIN_VK_ID, leader.id)
    assert excinfo.value.code == "guild_leader"
    assert await db_session.get(Character, leader.id) is not None  # ничего не удалено
    assert await db_session.scalar(select(AdminAction)) is None  # и в журнал не писали


@pytest.mark.asyncio
async def test_reset_allowed_for_ordinary_guild_member(db_session, make_character) -> None:
    leader = await make_character()
    member = await make_character()
    guild = Guild(name="Гильдия", tag="ГИЛ")
    db_session.add(guild)
    await db_session.flush()
    db_session.add(GuildMember(guild_id=guild.id, character_id=leader.id, rank=gc.RANK_LEADER))
    db_session.add(GuildMember(guild_id=guild.id, character_id=member.id, rank=gc.RANK_RECRUIT))
    await db_session.flush()

    await crs.reset_character(db_session, ADMIN_VK_ID, member.id)
    await db_session.commit()

    assert await db_session.get(Character, member.id) is None
    assert await db_session.get(Character, leader.id) is not None
    left = await db_session.scalar(select(GuildMember).where(GuildMember.character_id == leader.id))
    assert left is not None  # состав гильдии не тронут
