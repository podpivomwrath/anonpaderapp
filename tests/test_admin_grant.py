"""Выдача любого предмета из админки (патч 107)."""

import random

import pytest
from sqlalchemy import func, select

from game.economy import fishing
from models import CharacterFish, CharacterLootbox, Inventory, Item, User
from services import admin_grant_service as ag
from services import admin_service, wallet_service


def _all_keys() -> list[str]:
    keys = []
    for group in ag.catalog():
        for entry in group["entries"]:
            keys += [v["key"] for v in entry.get("variants", ())] or [entry["key"]]
    return keys


async def _vk_id(db, character) -> int:
    return await db.scalar(select(User.vk_id).where(User.id == character.user_id))


async def test_every_catalog_entry_can_be_granted(db_session, make_character) -> None:
    me = await make_character()
    admin = await _vk_id(db_session, me)
    for key in _all_keys():
        await ag.grant(db_session, admin, me, key, 1, None, random.Random(1))


async def test_gear_takes_rarity_slot_and_level(db_session, make_character) -> None:
    me = await make_character()
    await ag.grant(db_session, 0, me, "gear:boots:epic", 3, 42, random.Random(1))
    items = (await db_session.scalars(
        select(Item).join(Inventory, Inventory.item_id == Item.id).where(Inventory.character_id == me.id)
    )).all()
    assert [(i.slot, i.rarity, i.ilvl) for i in items] == [("boots", "epic", 42)] * 3


async def test_crafted_weapon_is_bound_and_named_by_spec(db_session, make_character) -> None:
    me = await make_character()
    await ag.grant(db_session, 0, me, "crafted:surgeon_scalpel:dps", 1, None, random.Random(1))
    item = await db_session.scalar(select(Item))
    assert item.bound and item.craft_spec == "dps" and item.craft_efficiency == 100
    assert item.name == "Тонкий скальпель"


async def test_fish_lands_in_its_grade(db_session, make_character) -> None:
    me = await make_character()
    await ag.grant(db_session, 0, me, "fish:ashen_roach:trophy", 1, None, random.Random(1))
    row = await db_session.scalar(select(CharacterFish))
    grade, _name, _mult = fishing.grade_for(fishing.fraction_of("ashen_roach", row.total_grams))
    assert (row.grade, grade) == ("trophy", "trophy")


async def test_chests_are_closed_and_in_bag(db_session, make_character) -> None:
    me = await make_character()
    await ag.grant(db_session, 0, me, "chest", 4, None, random.Random(1))
    count = await db_session.scalar(select(func.count()).select_from(CharacterLootbox).where(
        CharacterLootbox.character_id == me.id, CharacterLootbox.status == "closed",
    ))
    assert count == 4


async def test_gold_and_logging(db_session, make_character) -> None:
    me = await make_character(farm=10)
    note = await ag.grant(db_session, 0, me, "gold", 500, None, random.Random(1))
    assert (await wallet_service.get_wallet(db_session, me.id)).farm_currency == 510
    assert "×500" in note
    assert [a.action_type for a in await admin_service.action_journal(db_session)] == ["grant_any"]


async def test_service_items_only_to_self(db_session, make_character) -> None:
    me = await make_character()
    other = await make_character()
    admin = await _vk_id(db_session, me)
    with pytest.raises(admin_service.NotSelfTarget):
        await ag.grant(db_session, admin, other, "admin_weapon:guardian_quill", 1, None, random.Random(1))


async def test_bad_key_amount_and_duplicate_mount(db_session, make_character) -> None:
    me = await make_character()
    with pytest.raises(ag.GrantError):
        await ag.grant(db_session, 0, me, "gear:boots", 1, None, random.Random(1))
    with pytest.raises(ag.GrantError):
        await ag.grant(db_session, 0, me, "gear:boots:epic", ag.MAX_PIECES + 1, None, random.Random(1))
    with pytest.raises(ag.GrantError):
        await ag.grant(db_session, 0, me, "gold", 0, None, random.Random(1))
    await ag.grant(db_session, 0, me, "mount:ashen_steed", 1, None, random.Random(1))
    with pytest.raises(ag.GrantError):
        await ag.grant(db_session, 0, me, "mount:ashen_steed", 1, None, random.Random(1))
