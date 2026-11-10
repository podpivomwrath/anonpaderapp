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


async def test_class_change_returns_foreign_gear_rune(db_session, make_character) -> None:
    """Репорт 266: руна чужого класса после смены класса - в сумку, не действует."""
    from models import BaseClass
    from services import respec_service

    c = await make_character(level=10, base_class="warrior")
    _home(c)
    await rune_service.grant(db_session, c.id, "hammer_down")
    await rune_service.equip(db_session, c, rc.GEAR, "weapon:0", "hammer_down")
    await respec_service.full_class_reset(db_session, c, BaseClass("mage"))
    assert rune_service.effect(c, "hammer_down") == 0
    assert (await rune_service.bag(db_session, c.id)).get("hammer_down") == 1


def test_drop_rolls_only_ready_runes() -> None:
    rng = random.Random(3)
    for _ in range(300):
        assert rc.BY_ID[rune_service.roll_rune(rng)].ready


async def test_misfit_skill_rune_returns_to_bag(db_session, make_character) -> None:
    """2026-11-02: «Едкость» больше не встаёт в Токсичный выброс - стоявшая
    там руна при пересчёте уходит в сумку."""
    from models import CharacterRuneSlot

    c = await make_character(level=40, base_class="mage")
    c.subclass = "poisoner"
    db_session.add(CharacterRuneSlot(character_id=c.id, kind=rc.SKILL, slot="poisoner_toxic_burst:0", rune_id="acrid"))
    await db_session.flush()
    effects = await rune_service.recompute(db_session, c)
    assert "rune:acrid@poisoner_toxic_burst" not in effects
    assert (await rune_service._bag_row(db_session, c.id, "acrid")).count == 1


def test_calluses_adds_xp_on_small_numbers() -> None:
    """Репорт 327: round(5 * 1.06) = 5 - «Мозоли» на мелком опыте ничего не давали."""
    import random
    from types import SimpleNamespace

    from game.economy import runes

    c = SimpleNamespace(rune_effects={"rune:calluses": 0.06})
    rng = random.Random(7)
    total = sum(runes.craft_xp(c, 5, rng) for _ in range(5000))
    assert 26000 < total < 27000  # в среднем 5.3
    assert runes.craft_xp(SimpleNamespace(rune_effects={}), 5) == 5


async def test_preset_remembers_and_restores_runes(db_session, make_character) -> None:
    """Репорт 340: пресет запоминает раскладку рун и ставит её при
    переключении в родном городе; руны, которых нет, пропускает."""
    from models import CharacterBuffPreset
    from services import preset_service

    c = await make_character(level=10)
    _home(c)
    a, b, gone = [r.id for r in rc.RUNES if r.kind == rc.HERO][:3]
    for rid in (a, b, gone):
        await rune_service.grant(db_session, c.id, rid)
    await rune_service.equip(db_session, c, rc.HERO, "0", a)
    await rune_service.equip(db_session, c, rc.HERO, "1", gone)
    preset = CharacterBuffPreset(character_id=c.id, name="1", buff_ids=[], runes=None)
    db_session.add(preset)
    await db_session.flush()
    preset.runes = await rune_service.layout(db_session, c)
    # Переставил: руна a снята, в слот 0 - b, руна gone продана.
    await rune_service.unequip(db_session, c, rc.HERO, "1")
    await rune_service.take(db_session, c.id, gone)
    await rune_service.equip(db_session, c, rc.HERO, "0", b)
    note = await preset_service.apply_preset_runes(db_session, c, preset)
    assert "кроме 1 руны" in note
    placed = {(r.slot, r.rune_id) for r in await rune_service.slots(db_session, c.id)}
    assert placed == {("0", a)}
    bag = await rune_service.bag(db_session, c.id)
    assert bag.get(b) == 1 and a not in bag
    c.pos_x += 1
    assert "родном городе" in await preset_service.apply_preset_runes(db_session, c, preset)
