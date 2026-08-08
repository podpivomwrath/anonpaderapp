"""Инвентарь экипировки (патч 11, блок 2): список, карточка предмета, надевание.

Патч 13, ч.1: весь просмотр — ОДНО сообщение, редактируется на месте (список
→ карточка → назад → надеть), вместо каскада новых сообщений."""

from vkbottle.bot import BotLabeler, Message

from bot import editable_message
from bot.keyboards.items import INVENTORY_KEYBOARD_MAX_ITEMS, inventory_keyboard, item_view_keyboard, no_keyboard
from bot.keyboards.world import BTN_INVENTORY
from game.world import grid
from models import Item
from services import item_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_NS = "inventory"
_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _stats_line(item: Item) -> str:
    return " ".join(
        f"{item_service.STAT_LABELS[key].split()[0]}+{amount}"
        for key, amount in item.base_stats.items()
    )


async def _render_list(db, character) -> tuple[str, list[tuple[Item, bool]]]:
    items = await item_service.get_inventory(db, character.id)
    if not items:
        return "🎒 Твоя сумка пока пуста.", items
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
    if len(items) > INVENTORY_KEYBOARD_MAX_ITEMS:
        # Патч 32, баг 5: клавиатура показывает только первые N (лимит VK на
        # строки) — уточняем, что остальное не потеряно, просто не влезло сюда.
        text += (
            f"\n\n…и ещё {len(items) - INVENTORY_KEYBOARD_MAX_ITEMS} предмет(а/ов). "
            "Полный список и надевание — в мини-аппе."
        )
    return text, items


@labeler.message(text=[BTN_INVENTORY])
async def open_inventory(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is None:
            return  # инвентарь только в городе
        text, items = await _render_list(db, character)

    if not items:
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, no_keyboard())
        return
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, inventory_keyboard(items))


@labeler.message(payload_contains={"type": "inventory_item"})
async def view_item(message: Message) -> None:
    peer_id = message.peer_id
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
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, item_view_keyboard(item_id, entry.equipped),
    )


@labeler.message(payload_contains={"type": "inventory_back"})
async def back_to_list(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        text, items = await _render_list(db, character)

    if not items:
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, no_keyboard())
        return
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, inventory_keyboard(items))


@labeler.message(payload_contains={"type": "inventory_equip"})
async def equip_from_inventory(message: Message) -> None:
    peer_id = message.peer_id
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
        new_item = await db.get(Item, item_id)
        old_item = await item_service.equip_item(db, character.id, item_id)
        await db.commit()
        text, items = await _render_list(db, character)

    delta_line = item_service.stat_delta_line(old_item, new_item)
    full_text = f"Надето. {delta_line}\n\n{text}"
    keyboard = inventory_keyboard(items) if items else no_keyboard()
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, full_text, keyboard)
