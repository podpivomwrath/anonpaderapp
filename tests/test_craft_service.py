"""Патч 72: мастерская — работа с БД.

Чистый розыгрыш проверяется в test_crafting.py. Здесь — то, что происходит
вокруг него: списание руды, превращение предмета, привязка, лестница
инструментов и подорожание перекрафта.
"""

import random

import pytest

from game.economy import craft_config as cc
from models import CharacterOre, Inventory
from services import craft_service, item_service


async def _give_ore(db, character_id: int, ore_id: str, grade: str, count: int) -> None:
    db.add(CharacterOre(character_id=character_id, ore_id=ore_id, grade=grade, count=count))
    await db.flush()


async def _scalpel(db, character):
    return await item_service.grant_unique_item(
        db, character, "surgeon_scalpel", random.Random(1)
    )


def _rng() -> random.Random:
    return random.Random(42)


# --- Ковка ----------------------------------------------------------------------


async def test_craft_turns_the_scalpel_into_the_chosen_weapon(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 10)

    result = await craft_service.craft(
        db_session, character, item.id, cc.SPEC_TANK, "brown_iron", "common", _rng()
    )

    assert result.item.name == "Костяная пила"
    assert result.spec == cc.SPEC_TANK
    assert result.efficiency == cc.EFFICIENCY_MIN  # тир 1 -> 80%
    assert result.item.bound is True
    assert sum(result.stats.values()) > 0


async def test_craft_consumes_exactly_the_listed_ore(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 10)

    await craft_service.craft(
        db_session, character, item.id, cc.SPEC_DPS, "brown_iron", "common", _rng()
    )
    left = await craft_service.ore_amount(db_session, character.id, "brown_iron", "common")
    assert left == 10 - cc.CRAFT_ORE_COST


async def test_craft_without_enough_ore_changes_nothing(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 1)
    name_before = item.name

    with pytest.raises(craft_service.CraftError):
        await craft_service.craft(
            db_session, character, item.id, cc.SPEC_TANK, "brown_iron", "common", _rng()
        )
    assert item.name == name_before
    assert item.craft_spec is None


async def test_crafted_weapon_cannot_be_sold(db_session, make_character) -> None:
    """Лучшее оружие в игре должно добываться рейдом, а не покупкой."""
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 10)

    result = await craft_service.craft(
        db_session, character, item.id, cc.SPEC_SUPPORT, "brown_iron", "common", _rng()
    )
    assert item_service.is_unsellable(result.item) is True
    assert item_service.sell_price(result.item) == 0


async def test_better_ore_tier_starts_higher(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "taint_pyrite", "common", 10)

    result = await craft_service.craft(
        db_session, character, item.id, cc.SPEC_TANK, "taint_pyrite", "common", _rng()
    )
    assert result.efficiency == cc.EFFICIENCY_CRAFT_MAX  # тир 3 -> 100%


async def test_ore_above_the_craft_cap_is_refused(db_session, make_character) -> None:
    """Пепельное серебро в ковке сгорело бы впустую - упёрлось бы в тот же
    потолок 100%. Лучше отказать, чем молча сжечь дорогую руду."""
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "ashen_silver", "common", 10)

    with pytest.raises(craft_service.CraftError):
        await craft_service.craft(
            db_session, character, item.id, cc.SPEC_TANK, "ashen_silver", "common", _rng()
        )
    left = await craft_service.ore_amount(db_session, character.id, "ashen_silver", "common")
    assert left == 10, "отказ не должен ничего списывать"


async def test_craft_keeps_the_item_in_the_inventory(db_session, make_character) -> None:
    """Перекрафт мутирует тот же экземпляр - иначе надетость и счётчик
    перековок терялись бы на каждой операции."""
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 30)

    result = await craft_service.craft(
        db_session, character, item.id, cc.SPEC_TANK, "brown_iron", "common", _rng()
    )
    assert result.item.id == item.id
    entry = await db_session.scalar(
        Inventory.__table__.select().where(Inventory.item_id == item.id)
    )
    assert entry is not None


# --- Перекрафт ------------------------------------------------------------------


async def test_recraft_changes_spec_and_resets_efficiency(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "taint_pyrite", "common", 60)

    await craft_service.craft(
        db_session, character, item.id, cc.SPEC_TANK, "taint_pyrite", "common", _rng()
    )
    await _give_ore(db_session, character.id, "brown_iron", "common", 60)
    again = await craft_service.craft(
        db_session, character, item.id, cc.SPEC_DPS, "brown_iron", "common", _rng()
    )

    assert again.was_recraft is True
    assert again.item.craft_spec == cc.SPEC_DPS
    assert again.item.name == "Тонкий скальпель"
    assert again.efficiency == cc.EFFICIENCY_MIN, "процент обязан сброситься"


async def test_each_recraft_costs_more(db_session, make_character) -> None:
    """Иначе игрок за вечер добивает идеальный ролл."""
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 200)

    spent = []
    for spec in (cc.SPEC_TANK, cc.SPEC_DPS, cc.SPEC_SUPPORT, cc.SPEC_TANK):
        result = await craft_service.craft(
            db_session, character, item.id, spec, "brown_iron", "common", _rng()
        )
        spent.append(result.ore_spent)

    assert spent == sorted(spent)
    assert spent[1] > spent[0], "первый перекрафт дороже первой ковки"
    assert len(set(spent)) == len(spent)


async def test_recraft_does_not_inflate_the_budget(db_session, make_character) -> None:
    """Бюджет берётся от ИСХОДНОГО предмета. Считался бы он от текущих
    статов - каждая перековка делала бы оружие сильнее сама по себе."""
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "taint_pyrite", "common", 200)

    sums = []
    for spec in (cc.SPEC_TANK, cc.SPEC_DPS, cc.SPEC_SUPPORT):
        result = await craft_service.craft(
            db_session, character, item.id, spec, "taint_pyrite", "common", _rng()
        )
        sums.append(sum(result.stats.values()))
    assert len(set(sums)) == 1, f"сумма очков поехала между перековками: {sums}"


# --- Инструменты ----------------------------------------------------------------


async def test_tool_ceiling_follows_the_ore_tier(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    await _give_ore(db_session, character.id, "brown_iron", "common", 20)
    await _give_ore(db_session, character.id, "ashen_silver", "common", 20)

    assert await craft_service.make_tool(db_session, character, "brown_iron", "common") == 90
    assert await craft_service.make_tool(db_session, character, "ashen_silver", "common") == 120
    assert await craft_service.tools_of(db_session, character.id) == {90: 1, 120: 1}


async def test_tool_cost_grows_with_the_ceiling(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    await _give_ore(db_session, character.id, "brown_iron", "common", 100)
    await _give_ore(db_session, character.id, "ashen_silver", "common", 100)

    await craft_service.make_tool(db_session, character, "brown_iron", "common")
    cheap = 100 - await craft_service.ore_amount(db_session, character.id, "brown_iron", "common")
    await craft_service.make_tool(db_session, character, "ashen_silver", "common")
    dear = 100 - await craft_service.ore_amount(db_session, character.id, "ashen_silver", "common")
    assert dear > cheap


async def test_living_stone_is_not_a_tool(db_session, make_character) -> None:
    """Тир 6 оставлен под будущее пробуждение."""
    character = await make_character(base_class="warrior")
    await _give_ore(db_session, character.id, "living_stone", "common", 50)
    with pytest.raises(craft_service.CraftError):
        await craft_service.make_tool(db_session, character, "living_stone", "common")


# --- Улучшение ------------------------------------------------------------------


async def _crafted_at_80(db, character):
    item = await _scalpel(db, character)
    await _give_ore(db, character.id, "brown_iron", "common", 200)
    await craft_service.craft(
        db, character, item.id, cc.SPEC_TANK, "brown_iron", "common", _rng()
    )
    return item


async def test_upgrade_raises_one_step_and_spends_the_tool(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _crafted_at_80(db_session, character)
    await craft_service.make_tool(db_session, character, "brown_iron", "common")

    result = await craft_service.upgrade(db_session, character, item.id, 90)

    assert result.efficiency_before == 80
    assert result.efficiency_after == 90
    assert await craft_service.tools_of(db_session, character.id) == {}


async def test_upgrade_keeps_the_layout_and_grows_the_sum(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _crafted_at_80(db_session, character)
    before = dict(item.base_stats)
    await craft_service.make_tool(db_session, character, "brown_iron", "common")

    result = await craft_service.upgrade(db_session, character, item.id, 90)

    assert set(result.stats) == set(before)
    assert sum(result.stats.values()) > sum(before.values())


async def test_weak_tool_is_refused_and_not_spent(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _crafted_at_80(db_session, character)
    await _give_ore(db_session, character.id, "taint_pyrite", "common", 50)
    await craft_service.make_tool(db_session, character, "brown_iron", "common")  # потолок 90
    await craft_service.upgrade(db_session, character, item.id, 90)               # теперь 90

    await craft_service.make_tool(db_session, character, "brown_iron", "common")  # снова 90
    with pytest.raises(craft_service.CraftError):
        await craft_service.upgrade(db_session, character, item.id, 90)
    assert await craft_service.tools_of(db_session, character.id) == {90: 1}


async def test_climbing_to_the_cap_then_stopping(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _crafted_at_80(db_session, character)
    await _give_ore(db_session, character.id, "ashen_silver", "common", 200)

    for _ in range(4):
        await craft_service.make_tool(db_session, character, "ashen_silver", "common")
        await craft_service.upgrade(db_session, character, item.id, 120)

    assert item.craft_efficiency == cc.EFFICIENCY_MAX
    await craft_service.make_tool(db_session, character, "ashen_silver", "common")
    with pytest.raises(craft_service.CraftError):
        await craft_service.upgrade(db_session, character, item.id, 120)


async def test_upgrade_refuses_a_non_crafted_item(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await _scalpel(db_session, character)
    await _give_ore(db_session, character.id, "brown_iron", "common", 20)
    await craft_service.make_tool(db_session, character, "brown_iron", "common")

    with pytest.raises(craft_service.CraftError):
        await craft_service.upgrade(db_session, character, item.id, 90)


async def test_you_cannot_craft_from_someone_elses_item(db_session, make_character) -> None:
    owner = await make_character(base_class="warrior")
    thief = await make_character(base_class="mage")
    item = await _scalpel(db_session, owner)
    await _give_ore(db_session, thief.id, "brown_iron", "common", 50)

    with pytest.raises(craft_service.CraftError):
        await craft_service.craft(
            db_session, thief, item.id, cc.SPEC_TANK, "brown_iron", "common", _rng()
        )
