"""Патч 53: редкость «Уникальная» + выдача Скальпеля Хирурга.

Проверяем ИМЕННО инвариант, ради которого unique стоит ПОСЛЕДНЕЙ в
content/items/rarities.json (после admin): обычный премиум-апгрейд
(Метка Хранителя, item_gen.maybe_upgrade_rarity) НИКОГДА не должен
превратить обычный дроп в уникальный предмет — иначе Скальпель и будущие
рейд-уникумы переставали бы быть "не генерируются процедурно"."""

import random

from game.economy import item_gen
from services import item_service


class AlwaysUpgradeRng(random.Random):
    """rng.random() всегда 0.0 — maybe_upgrade_rarity гарантированно
    пытается повысить редкость (шанс не имеет значения)."""

    def random(self) -> float:
        return 0.0


def test_unique_rarity_is_registered_with_expected_shape() -> None:
    rarities = item_service.rarities()
    assert "unique" in rarities
    unique = rarities["unique"]
    assert unique.emoji == "🔴"
    assert unique.mult == 2.7
    assert unique.mult > rarities["legendary"].mult  # выше легендарной по силе


def test_legendary_premium_upgrade_never_reaches_unique() -> None:
    rarities = item_service.rarities()
    rng = AlwaysUpgradeRng()
    result = item_gen.maybe_upgrade_rarity("legendary", rarities, rng, chance=1.0)
    assert result != "unique"


def test_no_rarity_upgrades_into_unique_for_any_rollable_input() -> None:
    """Проходим по ВСЕМ редкостям, которые реально может вернуть roll_rarity
    (common..legendary) — ни одна не апгрейдится в unique одним броском."""
    rarities = item_service.rarities()
    rng = AlwaysUpgradeRng()
    for rarity_id in ("common", "uncommon", "rare", "epic", "legendary"):
        assert item_gen.maybe_upgrade_rarity(rarity_id, rarities, rng, chance=1.0) != "unique"


async def test_grant_unique_item_uses_class_primary_stat(db_session, make_character) -> None:
    warrior = await make_character(base_class="warrior")
    item = await item_service.grant_unique_item(db_session, warrior, "surgeon_scalpel")
    assert item.rarity == "unique"
    assert item.slot == "weapon"
    assert item.name == "Скальпель Хирурга"
    assert item.base_stats == {"str": 45}

    mage = await make_character(base_class="mage")
    mage_item = await item_service.grant_unique_item(db_session, mage, "surgeon_scalpel")
    assert mage_item.base_stats == {"int": 45}


async def test_unique_item_is_unsellable(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    item = await item_service.grant_unique_item(db_session, character, "surgeon_scalpel")
    assert item_service.is_unsellable(item) is True
    assert item_service.sell_price(item) == 0

    gold = await item_service.sell_item(db_session, character, item.id)
    assert gold == 0
    # Предмет НЕ удалён (продажа отказана целиком, не частично)
    still_there = await item_service.get_inventory_entry(db_session, character.id, item.id)
    assert still_there is not None


async def test_duplicate_unique_items_allowed(db_session, make_character) -> None:
    character = await make_character(base_class="rogue")
    first = await item_service.grant_unique_item(db_session, character, "surgeon_scalpel")
    second = await item_service.grant_unique_item(db_session, character, "surgeon_scalpel")
    assert first.id != second.id
    inventory = await item_service.get_inventory(db_session, character.id)
    assert sum(1 for item, _ in inventory if item.rarity == "unique") == 2
