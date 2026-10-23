"""Админка после ремесел (2026-10-21): карточка, уровень ремесла, выдача, обзор."""

import random

import pytest

from services import (
    admin_grant_service, admin_journal_text, admin_service, admin_systems_service, cooking_service, herb_service,
)


async def test_card_shows_crafts_house_and_bags(db_session, make_character) -> None:
    c = await make_character()
    await herb_service.add_herb(db_session, c.id, "bitter_wormwood", 3)
    await cooking_service.add_food(db_session, c.id, "wormwood_soup", "big", 2)
    c.house_work = "alchemy:heal_small"
    card = await admin_service.player_card(db_session, c.id)
    assert [x["title"] for x in card["crafts"]][2:] == ["🌿 Травничество", "⚗️ Алхимия", "🔥 Кулинария"]
    assert "Малое исцеление" in card["house"]["work"]
    assert card["herbs"][0]["count"] == 3 and card["food"][0]["grade"] == "крупная"
    assert card["flags"] == {"courier": False, "pocket": False, "donka": False, "subclass_declined": False}


async def test_set_craft_level_and_clear_work(db_session, make_character) -> None:
    c = await make_character()
    c.alchemy_xp = 5
    await admin_service.set_craft_level(db_session, 1, c, "alchemy", 30)
    assert (c.alchemy_level, c.alchemy_xp) == (30, 0)
    with pytest.raises(ValueError):
        await admin_service.set_craft_level(db_session, 1, c, "cooking", 51)
    c.house_work = "cook:wormwood_soup:common:1"
    await admin_service.clear_house_work(db_session, 1, c)
    assert c.house_work is None
    journal = await admin_service.action_journal(db_session, limit=5, target_character_id=c.id)
    texts = [admin_journal_text.describe(a, c.name) for a in journal]
    assert any("Алхимия уровень 30" in t for t in texts) and any("снял работу" in t for t in texts)


async def test_grant_herbs_food_and_purchases(db_session, make_character) -> None:
    c = await make_character()
    rng = random.Random(1)
    await admin_grant_service.grant(db_session, 1, c, "herb:stone_bloom", 4, None, rng)
    await admin_grant_service.grant(db_session, 1, c, "dish:monolith_feast:legendary", 2, None, rng)
    await admin_grant_service.grant(db_session, 1, c, "flag:has_house", 1, None, rng)
    assert c.has_house
    with pytest.raises(admin_grant_service.GrantError):
        await admin_grant_service.grant(db_session, 1, c, "flag:has_house", 1, None, rng)
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, c.id)] == [("stone_bloom", 4)]
    assert [(d.id, g, n) for d, _, g, n in await cooking_service.get_food(db_session, c.id)] == [
        ("monolith_feast", "legendary", 2)]


async def test_overview_has_crafts_block(db_session, make_character) -> None:
    await make_character()
    blocks = {b["title"]: b for b in await admin_systems_service.systems_stats(db_session)}
    assert "🌿 Ремесла и дом" in blocks
