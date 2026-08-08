"""Клавиатуры скупщика: трофеи (патч 9) + снаряжение (патч 11, блок 2).

INLINE (патч 13, ч.1) — окно скупщика редактируется на месте при поштучной
продаже, не плодит новых сообщений (см. bot/handlers/appraiser.py)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import TrophyDef
from models import Item

SELL_ALL_ID = "all"
BTN_SELL_GEAR = "🗡️ Продать снаряжение"


def no_keyboard() -> str:
    """Снять инлайн-кнопки с уже отредактированного сообщения (окно закрыто)."""
    return Keyboard(inline=True).get_json()


def appraiser_keyboard(stock: list[tuple[TrophyDef, int]]) -> str:
    kb = Keyboard(inline=True)
    if stock:
        total = sum(d.sell_price * count for d, count in stock)
        kb.add(
            Text(f"Продать всё — {total} зол.", payload={"type": "sell_trophies", "id": SELL_ALL_ID}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
        for trophy_def, count in stock:
            price = trophy_def.sell_price * count
            label = f"Продать {trophy_def.emoji} ×{count} — {price} зол."
            kb.add(
                Text(label, payload={"type": "sell_trophies", "id": trophy_def.id}),
                color=KeyboardButtonColor.SECONDARY,
            )
            kb.row()
    kb.add(Text(BTN_SELL_GEAR), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


# Патч 32, баг 5: тот же лимит VK (10 строк на клавиатуру), что и у
# инвентаря — см. bot/keyboards/items.py::INVENTORY_KEYBOARD_MAX_ITEMS.
SELL_GEAR_KEYBOARD_MAX_ITEMS = 9


def sell_gear_keyboard(items: list[tuple[Item, int]]) -> str:
    """items — (предмет, цена) НЕ надетых предметов инвентаря."""
    kb = Keyboard(inline=True)
    for item, price in items[:SELL_GEAR_KEYBOARD_MAX_ITEMS]:
        kb.add(
            Text(f"Продать {item.name} — {price} зол.", payload={"type": "sell_item", "item": item.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()
