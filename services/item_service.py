"""Базовая экипировка (патч 11, блок 2): дроп, инвентарь, экипировка, продажа.

Предметы дают только статы — не прокачиваются, не имеют пассивок. Отдельная
и куда более скромная система, чем будущий рейдовый гир 60+ (заточка/
пробуждение, models.Item.tier/enchant_level/awakened — этот патч их не трогает).
"""

import math
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.content_loader import ItemBaseDef, ItemRarityDef, load_item_bases, load_item_rarities
from game.economy import item_config as ic
from game.economy import item_gen
from models import Character, Inventory, Item
from services import wallet_service

SLOTS = ic.SLOTS

SLOT_TITLES = {
    "weapon": "Оружие",
    "helmet": "Шлем",
    "armor": "Доспех",
    "legs": "Штаны",
    "boots": "Сапоги",
}

STAT_ORDER = ["str", "agi", "int", "vit", "wil"]
STAT_LABELS = {
    "str": "💪 Сила",
    "agi": "🏃 Ловкость",
    "int": "🧠 Интеллект",
    "vit": "❤️ Выносливость",
    "wil": "✨ Воля",
}

_bases: dict[str, list[ItemBaseDef]] | None = None
_rarities: dict[str, ItemRarityDef] | None = None


def bases() -> dict[str, list[ItemBaseDef]]:
    global _bases
    if _bases is None:
        _bases = load_item_bases()
    return _bases


def rarities() -> dict[str, ItemRarityDef]:
    global _rarities
    if _rarities is None:
        _rarities = load_item_rarities()
    return _rarities


def rarity_def(rarity_id: str) -> ItemRarityDef:
    return rarities()[rarity_id]


def item_power(item: Item) -> int:
    """Суммарные очки статов предмета (item.base_stats уже их хранит)."""
    return sum(item.base_stats.values())


async def grant_from_kill(
    db: AsyncSession, character: Character, mob_level: int, rng: random.Random
) -> Item | None:
    """Дроп предмета с убитого моба — таблица НЕЗАВИСИМА от трофеев (патч 9).
    None — предмет не выпал. Новый предмет сразу в инвентаре, НЕ экипирован."""
    rarity_id = item_gen.roll_rarity(rng)
    if rarity_id is None:
        return None
    slot = item_gen.roll_slot(rng)
    primary_stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    generated = item_gen.generate_item(
        rng, ilvl=mob_level, slot=slot, rarity_id=rarity_id,
        primary_stat=primary_stat, bases=bases(), rarities=rarities(),
    )
    item = Item(
        name=generated.name, slot=generated.slot, base_stats=generated.base_stats,
        rarity=generated.rarity, ilvl=generated.ilvl,
    )
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=False))
    await db.flush()
    return item


async def get_equipped(db: AsyncSession, character_id: int) -> dict[str, Item | None]:
    """{slot: надетый предмет или None} — все 5 слотов, даже пустые."""
    rows = (
        await db.execute(
            select(Item)
            .join(Inventory, Inventory.item_id == Item.id)
            .where(Inventory.character_id == character_id, Inventory.equipped.is_(True))
        )
    ).scalars().all()
    equipped = {slot: None for slot in SLOTS}
    for item in rows:
        equipped[item.slot] = item
    return equipped


async def get_inventory(db: AsyncSession, character_id: int) -> list[tuple[Item, bool]]:
    """Все предметы персонажа (item, equipped), отсортированные по слоту и силе."""
    rows = (
        await db.execute(
            select(Item, Inventory.equipped)
            .join(Inventory, Inventory.item_id == Item.id)
            .where(Inventory.character_id == character_id)
        )
    ).all()
    items = [(item, equipped) for item, equipped in rows]
    items.sort(key=lambda pair: (SLOTS.index(pair[0].slot), -item_power(pair[0])))
    return items


async def get_inventory_entry(
    db: AsyncSession, character_id: int, item_id: int
) -> Inventory | None:
    return await db.scalar(
        select(Inventory).where(
            Inventory.character_id == character_id, Inventory.item_id == item_id
        )
    )


async def equip_item(db: AsyncSession, character_id: int, item_id: int) -> Item | None:
    """Надевает предмет (должен принадлежать персонажу); снимает старый в том же
    слоте (падает в инвентарь, не пропадает). Возвращает снятый предмет (или None)."""
    row = await get_inventory_entry(db, character_id, item_id)
    if row is None:
        return None
    new_item = await db.get(Item, item_id)
    if new_item is None:
        return None

    old_item = None
    equipped_rows = (
        await db.execute(
            select(Inventory, Item)
            .join(Item, Item.id == Inventory.item_id)
            .where(
                Inventory.character_id == character_id,
                Inventory.equipped.is_(True),
                Item.slot == new_item.slot,
            )
        )
    ).all()
    for old_row, old_item_row in equipped_rows:
        old_row.equipped = False
        old_item = old_item_row

    row.equipped = True
    await db.flush()
    return old_item


def sell_price(item: Item) -> int:
    """Цена скупщика: item_power * 3 * rarity_mult (только для отображения —
    сама продажа заново считает то же самое в sell_item)."""
    if item.rarity is None:
        return 0
    mult = rarity_def(item.rarity).mult
    return math.floor(item_power(item) * ic.SELL_PRICE_MULT * mult)


async def sell_item(db: AsyncSession, character: Character, item_id: int) -> int:
    """Продаёт ОДИН предмет скупщику (цена = item_power*3*rarity_mult). Надетые
    и чужие/несуществующие предметы продать нельзя (0 золота, ничего не меняется)."""
    row = await get_inventory_entry(db, character.id, item_id)
    if row is None or row.equipped:
        return 0
    item = await db.get(Item, item_id)
    if item is None or item.rarity is None:
        return 0
    gold = sell_price(item)
    await db.delete(row)
    await db.delete(item)
    await wallet_service.deposit(db, character.id, "farm", gold)
    await db.flush()
    return gold


def gear_bonus(equipped: dict[str, Item | None]) -> dict[str, int]:
    """Сумма статов всех надетых предметов — прибавляется к собственным статам
    персонажа при расчёте производных характеристик и в бою."""
    bonus: dict[str, int] = {}
    for item in equipped.values():
        if item is None:
            continue
        for stat, amount in item.base_stats.items():
            bonus[stat] = bonus.get(stat, 0) + amount
    return bonus


async def compute_gear_bonus(db: AsyncSession, character_id: int) -> dict[str, int]:
    """Удобный шорткат: get_equipped + gear_bonus одним вызовом."""
    equipped = await get_equipped(db, character_id)
    return gear_bonus(equipped)


# --- Тексты (окно сравнения при дропе, патч 11) ---


def format_drop_announcement(item: Item) -> str:
    emoji = rarity_def(item.rarity).emoji
    return f"🎁 С твари падает: {emoji} {item.name} (ур. {item.ilvl})"


def format_item_label(item: Item) -> str:
    emoji = rarity_def(item.rarity).emoji
    return f"{emoji} {item.name} (ур. {item.ilvl})"


def _arrow(before: int, after: int) -> str:
    if after > before:
        return "↑"
    if after < before:
        return "↓"
    return "="


def format_comparison(old_item: Item | None, new_item: Item) -> str:
    """Окно сравнения: было → стало по каждому стату + суммарная сила предмета."""
    old_label = format_item_label(old_item) if old_item is not None else "—"
    new_label = format_item_label(new_item)
    lines = [f"{SLOT_TITLES[new_item.slot]}:", f"{old_label}  →  {new_label}"]

    old_stats = old_item.base_stats if old_item is not None else {}
    new_stats = new_item.base_stats
    keys = [k for k in STAT_ORDER if k in old_stats or k in new_stats]
    for key in keys:
        before = old_stats.get(key, 0)
        after = new_stats.get(key, 0)
        delta = after - before
        lines.append(
            f"{STAT_LABELS[key]}  +{before}  →  +{after}   {_arrow(before, after)} ({delta:+d})"
        )

    old_power = sum(old_stats.values())
    new_power = sum(new_stats.values())
    lines.append("")
    lines.append(
        f"Итого сила предмета: {old_power} → {new_power} {_arrow(old_power, new_power)}"
    )
    return "\n".join(lines)
