"""Руны (2026-10-31, владелец - память runes-plan): пороги эффективности,
мастерство в игроке, вставка только дома, слоты за золото, PvP вполсилы."""

import random

import pytest

from game.economy import runes
from game.economy import runes_config as rc
from game.world import world_config as wc
from services import rune_service, wallet_service


def test_thresholds_match_owner_table() -> None:
    assert [runes.threshold("normal", k) for k in range(1, 5)] == [81, 800, 3200, 7200]
    assert runes.threshold("tight", 2) == 1600 and runes.threshold("very_tight", 1) == 324


def test_efficiency_is_linear_between_thresholds() -> None:
    assert runes.efficiency("normal", 0) == 1.0
    assert runes.efficiency("normal", 81) == pytest.approx(1.1)
    assert runes.efficiency("normal", 800) == pytest.approx(1.2)
    mid = runes.efficiency("normal", 2000)
    assert 1.2 < mid < 1.3
    assert runes.next_threshold("normal", 2000) == (3200, 130)


def test_every_rune_has_known_fields() -> None:
    for r in rc.RUNES:
        assert r.kind in rc.KINDS and r.rarity in rc.RARITY_WEIGHTS and r.curve in rc.CURVES
        assert r.pvp in rc.PVP_MULT and "{v}" in r.text
        assert not r.tag or r.tag in rc.SKILL_TAG_TITLES
    assert len({r.id for r in rc.RUNES}) == len(rc.RUNES)


def test_pvp_halves_and_drops() -> None:
    effects = {"rune:ash_skin": 0.04, "rune:heavy_gaze": 0.06, "rune:cast_cuirass": 0.25}
    scaled = runes.pvp_scaled(effects, pvp=True)
    assert scaled == {"rune:ash_skin": 0.02, "rune:cast_cuirass": 0.25}


def _home(character) -> None:
    character.region = "ridge"
    character.pos_x, character.pos_y = wc.CITY_COORDS["ridge"]


async def test_equip_only_at_home_and_mastery_stays(db_session, make_character) -> None:
    c = await make_character(level=10)
    await rune_service.grant(db_session, c.id, "ash_skin", 90)
    c.pos_x, c.pos_y, c.region = 30, 30, "ridge"
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.HERO, "0", "ash_skin")
    _home(c)
    await rune_service.equip(db_session, c, rc.HERO, "0", "ash_skin")
    assert rune_service.effect(c, "ash_skin") == pytest.approx(0.04)
    await rune_service.absorb(db_session, c, "ash_skin", 81)
    assert rune_service.effect(c, "ash_skin") == pytest.approx(0.044)
    await rune_service.unequip(db_session, c, rc.HERO, "0")
    assert rune_service.effect(c, "ash_skin") == 0
    # Мастерство осталось: вставил снова - снова 110%.
    await rune_service.equip(db_session, c, rc.HERO, "1", "ash_skin")
    assert rune_service.effect(c, "ash_skin") == pytest.approx(0.044)
    assert (await rune_service.bag(db_session, c.id)).get("ash_skin", 0) == 8


async def test_same_rune_twice_and_closed_slot_refused(db_session, make_character) -> None:
    c = await make_character(level=10)
    _home(c)
    await rune_service.grant(db_session, c.id, "ash_skin", 2)
    await rune_service.equip(db_session, c, rc.HERO, "0", "ash_skin")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.HERO, "1", "ash_skin")
    await rune_service.grant(db_session, c.id, "tight_purse")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.HERO, "4", "tight_purse")


async def test_buy_hero_slot_charges_gold(db_session, make_character) -> None:
    c = await make_character(level=10, farm=rc.HERO_SLOT_PRICES[0] + 5)
    assert await rune_service.buy_hero_slot(db_session, c) == 5
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 5
    with pytest.raises(rune_service.RuneError):
        await rune_service.buy_hero_slot(db_session, c)


async def test_gear_rune_class_and_place(db_session, make_character) -> None:
    c = await make_character(level=10, base_class="warrior")
    _home(c)
    await rune_service.grant(db_session, c.id, "thin_sting")
    await rune_service.grant(db_session, c.id, "hammer_down")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.GEAR, "weapon:0", "thin_sting")  # руна разбойника
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.GEAR, "helmet:0", "hammer_down")  # оружейная
    await rune_service.equip(db_session, c, rc.GEAR, "weapon:0", "hammer_down")
    assert rune_service.effect(c, "hammer_down") == pytest.approx(0.15)


async def test_skill_rune_second_slot_and_tag(db_session, make_character) -> None:
    c = await make_character(level=10, base_class="warrior", farm=rc.SKILL_SLOT_PRICE)
    _home(c)
    await rune_service.grant(db_session, c.id, "press", 2)
    await rune_service.equip(db_session, c, rc.SKILL, "warrior_cleave:0", "press")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, c, rc.SKILL, "warrior_cleave:1", "press")
    await rune_service.equip(db_session, c, rc.SKILL, "warrior_stagger:0", "press")
    assert rune_service.effect(c, "press", "warrior_stagger") == pytest.approx(0.10)
    await rune_service.grant(db_session, c.id, "grip")
    with pytest.raises(rune_service.RuneError):  # Хватка - только в контроль
        await rune_service.equip(db_session, c, rc.SKILL, "warrior_cleave:0", "grip")
    await rune_service.buy_skill_slot(db_session, c, "warrior_cleave")
    assert "warrior_cleave" in c.rune_skill_slots


def test_drop_rolls_only_ready_runes() -> None:
    rng = random.Random(3)
    for _ in range(300):
        assert rc.BY_ID[rune_service.roll_rune(rng)].ready
