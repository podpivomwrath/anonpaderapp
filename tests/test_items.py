"""Базовая экипировка (патч 11, блок 2): генерация, дроп, инвентарь, продажа."""

import random

from sqlalchemy import select

from game.content_loader import load_item_bases, load_item_rarities
from game.economy import item_config as ic
from game.economy import item_gen
from models import CharacterStats
from services import derived_stats_service, item_service, wallet_service


async def _stats(db_session, character) -> CharacterStats:
    return await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )


class FixedRng(random.Random):
    """rng.random() всегда возвращает заданное значение; choice — первый элемент."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value

    def choice(self, seq):
        return seq[0]


# --- game/economy/item_gen.py: чистая логика ---


def test_item_power_matches_patch_table() -> None:
    table = {
        1: [2, 2, 3, 3, 4],
        10: [4, 5, 6, 7, 9],
        20: [7, 8, 10, 12, 15],
        40: [12, 15, 18, 22, 27],
        60: [17, 21, 25, 31, 38],
    }
    mults = [1.0, 1.25, 1.5, 1.85, 2.25]
    for ilvl, expected_row in table.items():
        for mult, expected in zip(mults, expected_row):
            assert item_gen.item_power(ilvl, mult) == expected


def test_distribute_stats_single_stat_slot_gets_everything() -> None:
    assert item_gen.distribute_stats(10, "weapon", "int") == {"int": 10}
    assert item_gen.distribute_stats(10, "armor", "str") == {"vit": 10}


def test_distribute_stats_two_stat_slot_rounds_favor_first() -> None:
    # helmet: wil 60% / vit 40%
    assert item_gen.distribute_stats(7, "helmet", "str") == {"wil": 4, "vit": 3}
    assert item_gen.distribute_stats(10, "helmet", "str") == {"wil": 6, "vit": 4}
    # сумма всегда равна power
    for power in range(1, 20):
        stats = item_gen.distribute_stats(power, "boots", "agi")
        assert sum(stats.values()) == power


def test_distribute_stats_resolves_primary_by_owner_class() -> None:
    """Оружие/штаны падают "под класс" — основной стат владельца, не чужой."""
    assert item_gen.distribute_stats(10, "weapon", "str") == {"str": 10}
    assert item_gen.distribute_stats(10, "weapon", "agi") == {"agi": 10}
    legs_str = item_gen.distribute_stats(10, "legs", "str")
    assert "str" in legs_str and "vit" in legs_str


def test_roll_rarity_respects_drop_chance() -> None:
    class NeverDropRng(random.Random):
        def random(self) -> float:
            return 0.999  # выше ITEM_DROP_CHANCE (0.12)

    assert item_gen.roll_rarity(NeverDropRng()) is None


def test_roll_rarity_picks_common_on_low_roll() -> None:
    class AlwaysDropCommonRng(random.Random):
        def __init__(self) -> None:
            super().__init__()
            self._calls = 0

        def random(self) -> float:
            self._calls += 1
            return 0.0  # первый вызов: точно дропнуло; второй: первый интервал (common)

    assert item_gen.roll_rarity(AlwaysDropCommonRng()) == "common"


def test_roll_slot_uniform_from_five() -> None:
    rng = random.Random(1)
    slots = {item_gen.roll_slot(rng) for _ in range(200)}
    assert slots == set(ic.SLOTS)


def test_build_name_legendary_suffix_after_base_genitive() -> None:
    bases = load_item_bases()
    rarities = load_item_rarities()
    kirasa = next(b for b in bases["armor"] if b.name == "Кираса")
    name = item_gen.build_name(kirasa, rarities["legendary"])
    assert name == "Кираса Монолита"


def test_build_name_adjective_suffix_before_base_and_lowercased() -> None:
    bases = load_item_bases()
    rarities = load_item_rarities()
    klinok = next(b for b in bases["weapon"] if b.name == "Клинок")
    name = item_gen.build_name(klinok, rarities["rare"])
    assert name == "Кровавый клинок"


def test_generate_item_end_to_end() -> None:
    bases = load_item_bases()
    rarities = load_item_rarities()
    item = item_gen.generate_item(
        random.Random(1), ilvl=20, slot="armor", rarity_id="epic",
        primary_stat="int", bases=bases, rarities=rarities,
    )
    assert item.slot == "armor"
    assert item.rarity == "epic"
    assert item.ilvl == 20
    assert item.power == 12  # из таблицы патча
    assert item.base_stats == {"vit": 12}


# --- services/item_service.py: работа с БД ---


async def test_grant_from_kill_creates_unequipped_item(db_session, character_at) -> None:
    character = await character_at(50, 50, base_class="mage")

    class AlwaysDropWeaponCommonRng(random.Random):
        def __init__(self) -> None:
            super().__init__()

        def random(self) -> float:
            return 0.0  # дроп гарантирован + common

        def choice(self, seq):
            return seq[0]  # weapon первым в SLOTS

    item = await item_service.grant_from_kill(db_session, character, 20, AlwaysDropWeaponCommonRng())
    assert item is not None
    assert item.slot == "weapon"
    assert item.rarity == "common"
    assert item.base_stats == {"int": 7}  # ilvl=20 common power=7, mage primary=int

    equipped = await item_service.get_equipped(db_session, character.id)
    assert equipped["weapon"] is None  # новый предмет НЕ надет автоматически

    inventory = await item_service.get_inventory(db_session, character.id)
    assert len(inventory) == 1 and inventory[0][1] is False


async def test_grant_from_kill_none_when_rng_never_drops(db_session, character_at) -> None:
    character = await character_at(50, 50)

    class NeverDropRng(random.Random):
        def random(self) -> float:
            return 0.999

    item = await item_service.grant_from_kill(db_session, character, 20, NeverDropRng())
    assert item is None
    assert await item_service.get_inventory(db_session, character.id) == []


async def test_equip_item_swaps_old_out(db_session, character_at) -> None:
    character = await character_at(50, 50, base_class="warrior")
    first = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    await item_service.equip_item(db_session, character.id, first.id)

    # второй предмет того же слота (weapon, common) — гарантированный дроп
    second = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    assert second.slot == first.slot

    old = await item_service.equip_item(db_session, character.id, second.id)
    assert old.id == first.id

    equipped = await item_service.get_equipped(db_session, character.id)
    assert equipped["weapon"].id == second.id

    inventory = dict((item.id, eq) for item, eq in await item_service.get_inventory(db_session, character.id))
    assert inventory[first.id] is False  # старый вернулся в инвентарь, не пропал
    assert inventory[second.id] is True


async def test_gear_bonus_sums_equipped_items(db_session, character_at) -> None:
    character = await character_at(50, 50, base_class="mage")
    item = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    await item_service.equip_item(db_session, character.id, item.id)

    bonus = await item_service.compute_gear_bonus(db_session, character.id)
    assert bonus == item.base_stats


async def test_sell_item_credits_gold_and_removes_item(db_session, character_at) -> None:
    character = await character_at(50, 50, farm=0)
    item = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    expected_gold = item_service.sell_price(item)
    assert expected_gold > 0

    gold = await item_service.sell_item(db_session, character, item.id)
    assert gold == expected_gold

    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == expected_gold
    assert await item_service.get_inventory(db_session, character.id) == []


async def test_sell_item_equipped_rejected(db_session, character_at) -> None:
    character = await character_at(50, 50, farm=0)
    item = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    await item_service.equip_item(db_session, character.id, item.id)

    gold = await item_service.sell_item(db_session, character, item.id)
    assert gold == 0
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 0
    # предмет остался на месте, надет
    equipped = await item_service.get_equipped(db_session, character.id)
    assert equipped[item.slot] is not None


async def test_sell_item_unknown_or_foreign_rejected(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await item_service.sell_item(db_session, character, 999999) == 0


def test_format_comparison_empty_slot_shows_dash_and_full_gain() -> None:
    bases = load_item_bases()
    rarities = load_item_rarities()
    new_item_gen = item_gen.generate_item(
        random.Random(1), ilvl=20, slot="helmet", rarity_id="rare",
        primary_stat="int", bases=bases, rarities=rarities,
    )

    class _FakeItem:
        def __init__(self, gen) -> None:
            self.name = gen.name
            self.slot = gen.slot
            self.rarity = gen.rarity
            self.ilvl = gen.ilvl
            self.base_stats = gen.base_stats

    new_item = _FakeItem(new_item_gen)
    text = item_service.format_comparison(None, new_item)
    assert "—  →" in text
    assert "Итого сила предмета: 0 →" in text
    assert "↑" in text


def test_format_drop_announcement_includes_emoji_and_level() -> None:
    bases = load_item_bases()
    rarities = load_item_rarities()
    gen = item_gen.generate_item(
        random.Random(1), ilvl=15, slot="boots", rarity_id="legendary",
        primary_stat="agi", bases=bases, rarities=rarities,
    )

    class _FakeItem:
        name = gen.name
        rarity = gen.rarity
        ilvl = gen.ilvl

    text = item_service.format_drop_announcement(_FakeItem())
    assert "🟡" in text and "ур. 15" in text


# --- derived_stats_service: gear_bonus реально влияет на формулы ---


async def test_derived_stats_include_gear_bonus(db_session, character_at) -> None:
    character = await character_at(50, 50, base_class="mage")
    stats = await _stats(db_session, character)
    without_gear = derived_stats_service.compute(character, stats)

    item = await item_service.grant_from_kill(db_session, character, 20, FixedRng(0.0))
    await item_service.equip_item(db_session, character.id, item.id)
    bonus = await item_service.compute_gear_bonus(db_session, character.id)

    with_gear = derived_stats_service.compute(character, stats, bonus)
    assert with_gear.damage > without_gear.damage  # предмет добавил int (dmg-стат мага)
