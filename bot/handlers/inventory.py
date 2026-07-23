"""Инвентарь экипировки (патч 11, блок 2): список, карточка предмета, надевание."""

from vkbottle.bot import BotLabeler, Message

from bot.keyboards.items import inventory_keyboard, item_view_keyboard
from bot.keyboards.world import BTN_INVENTORY, city_menu_keyboard
from game.world import grid
from models import Item
from services import item_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()


def _stats_line(item: Item) -> str:
    return " ".join(
        f"{item_service.STAT_LABELS[key].split()[0]}+{amount}"
        for key, amount in item.base_stats.items()
    )


@labeler.message(text=[BTN_INVENTORY])
async def open_inventory(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is None:
            return  # инвентарь только в городе
        items = await item_service.get_inventory(db, character.id)

    if not items:
        await message.answer("🎒 Твоя сумка пока пуста.", keyboard=city_menu_keyboard(character))
        return

    lines = []
    for item, equipped in items:
        rarity = item_service.rarity_def(item.rarity)
        slot_title = item_service.SLOT_TITLES[item.slot]
        suffix = " (надето)" if equipped else ""
        lines.append(
            f"{rarity.emoji} {item.name} — {slot_title}, ур. {item.ilvl}{suffix}\n"
            f"{_stats_line(item)}"
        )
    text = "🎒 Инвентарь:\n\n" + "\n\n".join(lines)
    await message.answer(text, keyboard=inventory_keyboard(items))


@labeler.message(payload_contains={"type": "inventory_item"})
async def view_item(message: Message) -> None:
    payload = message.get_payload_json() or {}
    item_id = payload.get("item")
    if not isinstance(item_id, int):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        entry = await item_service.get_inventory_entry(db, character.id, item_id)
        if entry is None:
            return  # не принадлежит игроку / не существует
        item = await db.get(Item, item_id)
        if item is None:
            return
        old_item = None
        if not entry.equipped:
            equipped = await item_service.get_equipped(db, character.id)
            old_item = equipped[item.slot]

    if entry.equipped:
        text = f"{item_service.format_item_label(item)} — уже надето."
    else:
        text = item_service.format_comparison(old_item, item)
    await message.answer(text, keyboard=item_view_keyboard(item_id, entry.equipped))


@labeler.message(payload_contains={"type": "inventory_equip"})
async def equip_from_inventory(message: Message) -> None:
    payload = message.get_payload_json() or {}
    item_id = payload.get("item")
    if not isinstance(item_id, int):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        entry = await item_service.get_inventory_entry(db, character.id, item_id)
        if entry is None or entry.equipped:
            return
        await item_service.equip_item(db, character.id, item_id)
        await db.commit()

    await message.answer("Надето.", keyboard=city_menu_keyboard(character))
