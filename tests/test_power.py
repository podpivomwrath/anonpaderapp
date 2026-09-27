"""Патч 111: Мощь - статы + вещи, надбавки за подкласс и микробаффы."""

from models import CharacterBuffPreset, Inventory, Item
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


async def test_counts_stats_and_equipped_gear_but_not_service_items(db_session, make_character) -> None:
    me = await make_character()
    base = (await power_service.power_of(db_session, me)).total
    await _equip(db_session, me, {"str": 20, "vit": 10})
    await _equip(db_session, me, {"str": 1000}, slot="helmet", admin_only=True, rarity="admin")
    power = await power_service.power_of(db_session, me)
    assert power.gear == 30
    assert power.total == base + 30


async def test_subclass_and_active_buffs_add_percent(db_session, make_character) -> None:
    me = await make_character()
    before = (await power_service.power_of(db_session, me)).total
    me.subclass = "guardian"
    db_session.add(CharacterBuffPreset(character_id=me.id, name="П", buff_ids=["a", "b", "c", "d"], is_active=True))
    await db_session.flush()
    power = await power_service.power_of(db_session, me)
    assert power.buffs == 4
    assert power.total == round(before * (1 + 0.10 + 4 * 0.03))


def test_only_combat_boards_show_power() -> None:
    assert set(leaderboard_service.COMBAT_BOARDS) == {"pvp", "kills"}
