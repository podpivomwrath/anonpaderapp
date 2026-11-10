"""Патч 111: Мощь - статы + вещи, надбавки за подкласс и микробаффы."""

from models import Inventory, Item
from services import power_service
from services import leaderboard_service


def test_formula() -> None:
    plain = power_service.compute(200, 100, has_subclass=False, buffs=0)
    assert plain.total == 300
    full = power_service.compute(200, 100, has_subclass=True, buffs=5)
    assert full.total == round(300 * (1 + power_service.SUBCLASS_BONUS + 5 * power_service.PER_BUFF_BONUS))
    assert full.total > plain.total


async def _equip(db, character, stats: dict, **extra) -> Item:
    extra.setdefault("rarity", "epic")
    item = Item(name="Вещь", slot=extra.pop("slot", "weapon"), base_stats=stats, ilvl=60, **extra)
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=True))
    await db.flush()
    return item


async def test_counts_stats_and_equipped_gear(db_session, make_character) -> None:
    me = await make_character()
    base = (await power_service.power_of(db_session, me)).total
    await _equip(db_session, me, {"str": 20, "vit": 10})
    power = await power_service.power_of(db_session, me)
    assert power.gear == 30
    assert power.total == base + 30


async def test_subclass_and_skill_steps_add_percent(db_session, make_character) -> None:
    """Руны-навыки (2026-11-10): вместо баффов пресета - ступени вставленных
    рун-навыков, каждая ступень +3%, как прежний бафф."""
    me = await make_character()
    before = (await power_service.power_of(db_session, me)).total
    me.subclass = "guardian"
    me.rune_effects = {"ability:warrior_cleave": 1, "step:warrior_cleave": 3, "ability:guardian_block": 2,
                       "step:guardian_block": 1}
    await db_session.flush()
    power = await power_service.power_of(db_session, me)
    assert power.buffs == 4
    assert power.total == round(before * (1 + 0.10 + 4 * 0.03))


async def test_power_is_current_not_best_ever(db_session, make_character) -> None:
    """Мощь - по тому, что надето СЕЙЧАС: сняли - упала, надели слабее - меньше."""
    from services import item_service

    me = await make_character()
    naked = (await power_service.power_of(db_session, me)).total
    strong = await _equip(db_session, me, {"str": 40})
    with_strong = (await power_service.power_of(db_session, me)).total
    assert with_strong == naked + 40

    assert await item_service.unequip_item(db_session, me.id, strong.id)
    assert (await power_service.power_of(db_session, me)).total == naked
    assert not await item_service.unequip_item(db_session, me.id, strong.id), "уже снята"

    weak = Item(name="Слабая", slot="weapon", base_stats={"str": 10}, rarity="common", ilvl=1)
    db_session.add(weak)
    await db_session.flush()
    db_session.add(Inventory(character_id=me.id, item_id=weak.id, equipped=False))
    await db_session.flush()
    await item_service.equip_item(db_session, me.id, weak.id)
    assert (await power_service.power_of(db_session, me)).total == naked + 10


def test_only_combat_boards_show_power() -> None:
    assert set(leaderboard_service.COMBAT_BOARDS) == {"pvp", "kills"}
