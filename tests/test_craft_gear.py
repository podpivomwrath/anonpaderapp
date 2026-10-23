"""Ремесленные инструменты (2026-10-23, решения владельца)."""

import random

import pytest

from game.economy import craft_gear, fishing, herbalism, mining
from game.economy import craft_gear_config as gc
from services import craft_gear_service, herb_service, mining_service


def _ore(tier: int) -> str:
    return next(o.id for o in mining.ore_defs_ordered() if o.tier == tier)


def _herb(tier: int) -> str:
    return next(h.id for h in herbalism.herb_defs_ordered() if h.tier == tier)


async def test_sickle_forged_from_tier1_ore_and_upgrades_by_tier(db_session, make_character) -> None:
    c = await make_character()
    await mining_service.add_ore(db_session, c.id, _ore(1), "common", gc.TOOLS["sickle"].cost)
    row = await craft_gear_service.make(db_session, c, "sickle", 1)
    assert row.tier == 1 and await craft_gear_service.ore_have(db_session, c.id, 1) == 0
    # Тот же тир второй раз - отказ; тир выше без уровня - отказ.
    with pytest.raises(craft_gear_service.GearError):
        await craft_gear_service.make(db_session, c, "sickle", 1)
    await mining_service.add_ore(db_session, c.id, _ore(2), "common", 50)
    with pytest.raises(craft_gear_service.GearError, match="уровень"):
        await craft_gear_service.make(db_session, c, "sickle", 2)
    c.herbalism_level = gc.TIER_LEVEL_50[2]
    assert (await craft_gear_service.make(db_session, c, "sickle", 2)).tier == 2


async def test_not_enough_material_spends_nothing(db_session, make_character) -> None:
    c = await make_character()
    await mining_service.add_ore(db_session, c.id, _ore(1), "common", 2)
    with pytest.raises(craft_gear_service.GearError):
        await craft_gear_service.make(db_session, c, "pick", 1)
    assert await craft_gear_service.ore_have(db_session, c.id, 1) == 2


async def test_spices_charges_spent_on_eating_boost_the_buff(db_session, make_character) -> None:
    c = await make_character()
    await herb_service.add_herb(db_session, c.id, _herb(1), gc.TOOLS["spices"].cost)
    row = await craft_gear_service.make(db_session, c, "spices", 1)
    assert row.count == gc.TOOLS["spices"].yield_
    assert await craft_gear_service.use_charge(db_session, c.id, "spices") == 1
    assert row.count == gc.TOOLS["spices"].yield_ - 1


async def test_drops_are_granted_once(db_session, make_character) -> None:
    c = await make_character()

    class Lucky(random.Random):
        def random(self):
            return 0.0

    assert await craft_gear_service.roll_almanac(db_session, c, Lucky()) == craft_gear_service.ALMANAC_LINE
    assert await craft_gear_service.roll_almanac(db_session, c, Lucky()) is None
    assert await craft_gear_service.tier(db_session, c.id, "almanac") == 1


def test_pick_and_rod_and_line_effects() -> None:
    assert craft_gear.pick_speed(3, 3) == pytest.approx(0.18)
    assert craft_gear.pick_speed(2, 5) == pytest.approx(0.06)  # ниже тира рудника - вдвое
    assert craft_gear.pick_speed(0, 1) == 0
    assert craft_gear.line_break_mult(5) == pytest.approx(0.7)
    # Удочка тянет рыбу тиром выше, но не выше тира озера.
    rng = random.Random(1)
    fc = fishing.fc
    up = {fishing.roll_fish_id(rng, 2, 1, 1.0) for _ in range(300)} - {fc.NAMELESS_ID}
    assert up <= set(fc.LAKE_POOLS[2]) and not up <= set(fc.LAKE_POOLS[1])
    capped = {fishing.roll_fish_id(rng, 1, 1, 1.0) for _ in range(300)} - {fc.NAMELESS_ID}
    assert capped <= set(fc.LAKE_POOLS[1])


async def test_pick_makes_digging_faster(db_session, character_at) -> None:
    mine = next(m for m in mining.all_mines() if m.tier == 1)
    c = await character_at(mine.x, mine.y)
    await mining_service.refill_all_veins(db_session, 10)
    plain = await mining_service.start_dig(db_session, c, mine, random.Random(1))
    await mining_service.cancel_dig(db_session, c)
    from models import CharacterCraftGear

    db_session.add(CharacterCraftGear(character_id=c.id, tool_id="pick", tier=1, count=0))
    await db_session.flush()
    faster = await mining_service.start_dig(db_session, c, mine, random.Random(1))
    assert faster.seconds == pytest.approx(plain.seconds * (1 - gc.PICK_SPEED_PER_TIER))
