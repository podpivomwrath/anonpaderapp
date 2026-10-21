"""Кулинария (2026-10-21): готовка из рыбы, еда в инвентаре, бафф."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.handlers import house as house_handlers
from game.combat.session import Stats, build_combatant
from game.economy import cooking
from game.economy import cooking_config as cc
from models import CharacterFish
from services import cooking_service, daily_service, herb_service, preset_service, vitals_service, wallet_service

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


async def _fish(db, cid, fish_id, grade, grams):
    db.add(CharacterFish(character_id=cid, fish_id=fish_id, grade=grade, total_grams=grams))
    await db.flush()


def test_catalog_no_yo_and_dishes_known() -> None:
    for dish in cc.DISHES:
        d = cooking.dish_def(dish.dish_id)
        assert d is not None and "ё" not in (d.name + d.description).lower()
    assert cooking.buff_text(cc.DISHES_BY_ID["wormwood_soup"], "legendary") == "+20% здоровья"
    assert cooking.food_minutes(9) == 30 and cooking.food_minutes(50) == 60
    # Градации - рыбьи (мелочь ... легендарная), а не рудные.
    from game.economy import fishing_config as fc

    assert set(cc.GRADE_MULT) == set(cc.GRADE_ORDER) == {g[1] for g in fc.GRADES}


async def test_cook_from_fish_portions_by_weight(db_session, make_character) -> None:
    c = await make_character(farm=500)
    await _fish(db_session, c.id, "pale_perch", "big", 1800)
    await _fish(db_session, c.id, "blind_gudgeon", "common", 300)  # меньше порции - не предлагается
    await herb_service.add_herb(db_session, c.id, "bitter_wormwood", 1)
    dish = cc.DISHES_BY_ID["wormwood_soup"]
    options = await cooking_service.fish_options(db_session, c.id, dish)
    assert [(o.fish.id, o.portions) for o in options] == [("pale_perch", 3)]
    await cooking_service.start(db_session, c, "wormwood_soup", "pale_perch", "big", NOW)
    assert cooking_service.cooking_now(c) == (dish, "big", 3)
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 480
    assert [x.id for x in await cooking_service.due(db_session, NOW + timedelta(seconds=31))] == [c.id]
    res = await cooking_service.finish(db_session, c)
    assert res.portions == 3 and res.xp == 22
    food = await cooking_service.get_food(db_session, c.id)
    assert [(d.id, g, n) for d, _, g, n in food] == [("wormwood_soup", "big", 3)]
    assert "×3" in house_handlers.cooked_text(res)


async def test_cook_refusals_keep_everything(db_session, make_character) -> None:
    c = await make_character(farm=500)
    await _fish(db_session, c.id, "pale_perch", "common", 1000)
    with pytest.raises(cooking_service.CookingError, match="травы"):
        await cooking_service.start(db_session, c, "wormwood_soup", "pale_perch", "common", NOW)
    with pytest.raises(cooking_service.CookingError, match="не знаком"):
        await cooking_service.start(db_session, c, "monolith_feast", "pale_perch", "common", NOW)
    with pytest.raises(cooking_service.CookingError, match="не подходит"):
        c.cooking_level = 12
        await cooking_service.start(db_session, c, "orache_stew", "pale_perch", "common", NOW)
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 500


async def test_eat_gives_buff_replaces_old_and_reaches_combat(db_session, make_character) -> None:
    c = await make_character()
    await cooking_service.add_food(db_session, c.id, "wormwood_soup", "trophy", 1)
    await cooking_service.add_food(db_session, c.id, "orache_stew", "common", 1)
    await cooking_service.eat(db_session, c, "wormwood_soup", "trophy")
    assert cooking_service.buff(c) == {"max_hp_bonus": 0.15}
    from models import CharacterStats
    from sqlalchemy import select

    cs = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == c.id))
    with_food = vitals_service.max_hp(c, cs)
    await cooking_service.eat(db_session, c, "orache_stew", "common")
    assert cooking_service.buff(c) == {"damage_bonus": 0.05}  # новое заменило старое
    assert vitals_service.max_hp(c, cs) < with_food
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods.get("damage_bonus") == pytest.approx(0.05)
    with pytest.raises(cooking_service.CookingError):
        await cooking_service.eat(db_session, c, "orache_stew", "common")
    c.food_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cooking_service.buff(c) == {}


def test_max_hp_bonus_applies_in_combatant() -> None:
    stats = Stats(strength=10, agility=10, intellect=10, vitality=10, will=10)
    plain = build_combatant(1, 0, "character", "a", 20, stats, "str", base_class="warrior")
    fed = build_combatant(1, 0, "character", "a", 20, stats, "str", base_class="warrior",
                          buff_modifiers={"max_hp_bonus": 0.10})
    assert fed.max_hp == round(plain.max_hp * 1.1)


def test_oven_and_fish_keyboards_fit_vk() -> None:
    rows = json.loads(house_handlers.oven_keyboard(cc.MAX_LEVEL))["buttons"]
    assert len(rows) <= 5 and all(len(r) <= 3 for r in rows)


async def test_craft_dailies_need_house_and_are_fixed(db_session, make_character) -> None:
    c = await make_character(level=60)
    pool = {q.id for q in daily_service._eligible_pool(c)}
    assert "herbalist" in pool and "brewer" not in pool and "home_cook" not in pool
    c.has_house = True
    assert {"brewer", "home_cook"} <= {q.id for q in daily_service._eligible_pool(c)}
