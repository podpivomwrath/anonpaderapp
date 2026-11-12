"""Заточка кованых уникалок (2026-11-13, владелец): +1 или откат, шанс отката
от градации руды, цена - звёздная пыль и руда высоких тиров."""

import random

import pytest

from game.economy import craft_config as cc
from game.economy import crafting
from game.economy import enchant_config as ec
from models import CharacterOre, ItemUpgradeHistory
from services import craft_service, item_service


class FixedRng(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def random(self) -> float:
        return self._value


WIN = FixedRng(0.99)   # выше любого шанса отката
LOSE = FixedRng(0.0)   # ниже любого


async def _forged(db, make_character, dust=100, crimson=50, stone=50):
    character = await make_character(base_class="warrior")
    character.star_dust = dust
    item = await item_service.grant_unique_item(db, character, "surgeon_scalpel", random.Random(1))
    for ore_id, count in (("brown_iron", 10), (ec.LOW_ORE, crimson), (ec.HIGH_ORE, stone)):
        db.add(CharacterOre(character_id=character.id, ore_id=ore_id, grade="common", count=count))
    await db.flush()
    await craft_service.craft(db, character, item.id, cc.SPEC_DPS, "brown_iron", "common", random.Random(42))
    return character, item


def test_costs_grow_and_ore_switches_at_six() -> None:
    assert [ec.dust_cost(t) for t in (1, 2, 10)] == [3, 4, 12]
    assert ec.ore_cost(1) == (ec.LOW_ORE, 1) and ec.ore_cost(5) == (ec.LOW_ORE, 5)
    assert ec.ore_cost(6) == (ec.HIGH_ORE, 1) and ec.ore_cost(10) == (ec.HIGH_ORE, 5)
    assert ec.ROLLBACK["common"] > ec.ROLLBACK["rare"] > ec.ROLLBACK["epic"] > ec.ROLLBACK["legendary"]


def test_each_level_adds_two_percent() -> None:
    base = {"str": 100, "vit": 50}
    assert crafting.crafted_stats(base, 100, 0) == base
    assert crafting.crafted_stats(base, 100, 10) == {"str": 120, "vit": 60}
    assert crafting.crafted_stats(base, 110, 5)["str"] == 121  # 100 × 1.1 × 1.1


async def test_success_raises_level_and_stats(db_session, make_character) -> None:
    character, item = await _forged(db_session, make_character)
    before = sum(item.base_stats.values())
    result = await craft_service.enchant(db_session, character, item.id, "common", WIN)
    assert result.success and item.enchant_level == 1
    assert item.base_stats == crafting.crafted_stats(item.craft_base_stats, item.craft_efficiency, 1)
    assert sum(item.base_stats.values()) >= before
    assert character.star_dust == 100 - ec.dust_cost(1)
    assert await craft_service.ore_amount(db_session, character.id, ec.LOW_ORE, "common") == 50 - 1
    assert item_service.display_name(item).endswith(" +1")


async def test_failure_rolls_back_one_step_not_below_zero(db_session, make_character) -> None:
    character, item = await _forged(db_session, make_character)
    await craft_service.enchant(db_session, character, item.id, "common", LOSE)
    assert item.enchant_level == 0
    for _ in range(3):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)
    await craft_service.enchant(db_session, character, item.id, "common", LOSE)
    assert item.enchant_level == 2
    history = (await db_session.execute(
        ItemUpgradeHistory.__table__.select().where(ItemUpgradeHistory.item_id == item.id)
    )).all()
    assert len(history) == 5


async def test_living_stone_from_six_and_cap(db_session, make_character) -> None:
    character, item = await _forged(db_session, make_character, dust=500)
    for _ in range(ec.MAX_LEVEL):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)
    assert item.enchant_level == ec.MAX_LEVEL
    assert await craft_service.ore_amount(db_session, character.id, ec.HIGH_ORE, "common") == 50 - 15
    assert craft_service.enchant_cost(character, item) is None
    with pytest.raises(craft_service.CraftError, match="выше не бывает"):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)


async def test_not_enough_dust_spends_nothing(db_session, make_character) -> None:
    character, item = await _forged(db_session, make_character, dust=2)
    with pytest.raises(craft_service.CraftError, match="пыли"):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)
    await db_session.rollback()


async def test_unforged_item_cannot_be_enchanted(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    character.star_dust = 50
    item = await item_service.grant_unique_item(db_session, character, "surgeon_scalpel", random.Random(1))
    db_session.add(CharacterOre(character_id=character.id, ore_id=ec.LOW_ORE, grade="common", count=5))
    await db_session.flush()
    with pytest.raises(craft_service.CraftError, match="выкованную"):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)


async def test_enchant_survives_upgrade_and_recraft(db_session, make_character) -> None:
    character, item = await _forged(db_session, make_character)
    for _ in range(2):
        await craft_service.enchant(db_session, character, item.id, "common", WIN)
    db_session.add(CharacterOre(character_id=character.id, ore_id="brown_iron", grade="rare", count=50))
    await db_session.flush()
    await craft_service.craft(db_session, character, item.id, cc.SPEC_TANK, "brown_iron", "rare", random.Random(3))
    assert item.enchant_level == 2
    assert item.base_stats == crafting.crafted_stats(item.craft_base_stats, item.craft_efficiency, 2)
