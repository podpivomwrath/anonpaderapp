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
    # Второй раз - уже не альманах, а страница к нему (2026-10-29).
    assert "Страница" in await craft_gear_service.roll_almanac(db_session, c, Lucky())
    assert await craft_gear_service.tier(db_session, c.id, "almanac") == 1


async def test_almanac_rolls_once_in_raid_and_rift(db_session, make_character, monkeypatch) -> None:
    """2026-10-23: альманах и с рейдов/разломов, один бросок за этап -
    множитель добычи рейда его не умножает."""
    from services import raid_combat_service

    c = await make_character(level=30)
    c.pos_x, c.pos_y = 15, 0
    calls = []
    real = craft_gear_service.roll_almanac

    async def counted(db, character, rng):
        calls.append(character.id)
        return await real(db, character, rng)

    monkeypatch.setattr(craft_gear_service, "roll_almanac", counted)
    monkeypatch.setattr(gc, "ALMANAC_DROP_CHANCE", 1.0)
    rewards = await raid_combat_service.reward_mob_kill(db_session, [c], 30, random.Random(1), 3)
    assert calls == [c.id]
    assert craft_gear_service.ALMANAC_LINE in rewards[0].elixir_lines


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


async def test_bait_made_by_cook_speeds_up_bites(db_session, make_character) -> None:
    from services import fishing_service

    c = await make_character()
    await herb_service.add_herb(db_session, c.id, _herb(1), 1)
    from models import CharacterFish

    db_session.add(CharacterFish(character_id=c.id, fish_id="ashen_roach", grade="common", total_grams=400))
    await db_session.flush()
    row = await craft_gear_service.make(db_session, c, "bait", 1)
    assert row.count == gc.TOOLS["bait"].yield_
    assert craft_gear_service.bite_mult(c) == 1.0
    assert await craft_gear_service.use_bait(db_session, c) == gc.BAIT_MINUTES
    assert craft_gear_service.bite_mult(c) == pytest.approx(1 - gc.BAIT_SPEED)
    lake = fishing.all_lakes()[0]
    slow = fishing_service.start_cast(c, lake, random.Random(5)).seconds
    fast = fishing_service.start_cast(c, lake, random.Random(5), bite_mult=craft_gear_service.bite_mult(c)).seconds
    assert fast == pytest.approx(slow * (1 - gc.BAIT_SPEED))


def test_flask_spreads_elixir_to_group_weaker() -> None:
    from game.combat import elixir_effects
    from game.combat.session import EffectKind
    from tests.conftest import combatant

    a, b = combatant(1, side=0), combatant(2, side=0)
    foe = combatant(3, side=1)
    everyone = {1: a, 2: b, 3: foe}
    elixir_effects.throw_flask(a, "ashen_haze", everyone, gc.FLASK_POWER)
    solo = combatant(4, side=0)
    elixir_effects.apply_combat_elixir(solo, "ashen_haze")
    full = solo.effects_of(EffectKind.DODGE)[0].value
    assert a.effects_of(EffectKind.DODGE)[0].value == pytest.approx(full * gc.FLASK_POWER)
    assert b.effects_of(EffectKind.DODGE) and not foe.effects_of(EffectKind.DODGE)
    # Лечение - каждому, слабее.
    a.current_hp = b.current_hp = 1
    elixir_effects.throw_flask(a, "heal_large", everyone, gc.FLASK_POWER)
    assert 1 < a.current_hp < a.max_hp and b.current_hp > 1


def test_last_breath_is_not_throwable() -> None:
    """2026-10-23, владелец: «Последний вздох» склянкой на группу - слишком сильно."""
    from types import SimpleNamespace

    from bot import flask_throw

    assert not flask_throw.can_throw(SimpleNamespace(id="last_breath", category="combat"))
    assert flask_throw.can_throw(SimpleNamespace(id="second_heart", category="combat"))
    assert not flask_throw.can_throw(SimpleNamespace(id="scroll_ward", category="scroll"))


async def test_almanac_ten_hints_then_an_hour_of_charging(db_session, make_character) -> None:
    """2026-10-29, владелец: 10 подсказок, потом час зарядки, потом снова 10."""
    from datetime import datetime, timedelta, timezone

    from services import craft_gear_service

    c = await make_character(level=20)
    await craft_gear_service.grant_drop(db_session, c.id, "almanac")
    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    left = [(await craft_gear_service.almanac_use(db_session, c.id, now))[0] for _ in range(10)]
    assert left == [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert await craft_gear_service.almanac_use(db_session, c.id, now + timedelta(minutes=59)) is None
    assert await craft_gear_service.almanac_use(db_session, c.id, now + timedelta(minutes=61)) == (9, 10)


async def test_almanac_page_drops_only_to_owner_and_adds_two(db_session, make_character) -> None:
    import random

    from services import craft_gear_service

    class Lucky(random.Random):
        def random(self) -> float:
            return 0.0

    c = await make_character(level=20)
    first = await craft_gear_service.roll_almanac(db_session, c, Lucky())
    assert first == craft_gear_service.ALMANAC_LINE  # сначала сам альманах
    page = await craft_gear_service.roll_almanac(db_session, c, Lucky())
    assert page and "Страница" in page and "12" in page
    assert (await craft_gear_service.almanac_use(db_session, c.id)) == (11, 12)


async def test_almanac_hints_each_patch_once(db_session, make_character) -> None:
    """2026-10-29, владелец: на один куст альманах указывает один раз;
    сорванный куст из памяти уходит."""
    from datetime import datetime, timezone

    from sqlalchemy import delete

    from models import HerbPatch
    from services import craft_gear_service

    c = await make_character(level=20)
    await craft_gear_service.grant_drop(db_session, c.id, "almanac")
    now = datetime.now(timezone.utc)
    a = HerbPatch(x=50, y=50, herb_id="bitter_wormwood", spawned_at=now)
    b = HerbPatch(x=51, y=50, herb_id="ash_plantain", spawned_at=now)
    db_session.add_all([a, b])
    await db_session.flush()
    assert await craft_gear_service.almanac_not_hinted(db_session, c.id, {a.id, b.id}) == {a.id, b.id}
    await craft_gear_service.almanac_mark_hinted(db_session, c.id, {a.id})
    assert await craft_gear_service.almanac_not_hinted(db_session, c.id, {a.id, b.id}) == {b.id}
    await db_session.execute(delete(HerbPatch).where(HerbPatch.id == a.id))
    await craft_gear_service.almanac_mark_hinted(db_session, c.id, {b.id})
    row = await craft_gear_service._row(db_session, c.id, "almanac")
    assert row.hinted == str(b.id)


async def test_almanac_herb_filter_only_seen_herbs(db_session, make_character) -> None:
    """2026-10-29, владелец: галочки по траве; пусто - альманах молчит."""
    import pytest

    from services import craft_gear_service

    c = await make_character(level=20)
    c.herbalism_level = 12  # различает I и II тир
    with pytest.raises(craft_gear_service.GearError):
        await craft_gear_service.set_almanac_herbs(db_session, c, ["salt_orache"])  # альманаха нет
    await craft_gear_service.grant_drop(db_session, c.id, "almanac")
    await craft_gear_service.set_almanac_herbs(db_session, c, ["salt_orache", "bitter_wormwood"])
    assert await craft_gear_service.almanac_filter(db_session, c.id) == {"salt_orache", "bitter_wormwood"}
    with pytest.raises(craft_gear_service.GearError):
        await craft_gear_service.set_almanac_herbs(db_session, c, ["ash_poppy"])  # IV тир не различает
    await craft_gear_service.set_almanac_herbs(db_session, c, [])
    assert await craft_gear_service.almanac_filter(db_session, c.id) == set()
    # Отмечена вся различимая трава - это «вся», и новая трава попадёт сама.
    await craft_gear_service.set_almanac_herbs(
        db_session, c, ["bitter_wormwood", "ash_plantain", "salt_orache", "rusty_thistle"],
    )
    assert await craft_gear_service.almanac_filter(db_session, c.id) is None
    await craft_gear_service.set_almanac_herbs(db_session, c, None)
    assert await craft_gear_service.almanac_filter(db_session, c.id) is None
