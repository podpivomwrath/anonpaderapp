"""Клавиатуры скупщика: трофеи (патч 9) + снаряжение (патч 11, блок 2)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import TrophyDef
from models import Item

SELL_ALL_ID = "all"
BTN_SELL_GEAR = "🗡️ Продать снаряжение"


def appraiser_keyboard(stock: list[tuple[TrophyDef, int]]) -> str:
    kb = Keyboard(one_time=False)
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


def sell_gear_keyboard(items: list[tuple[Item, int]]) -> str:
    """items — (предмет, цена) НЕ надетых предметов инвентаря."""
    kb = Keyboard(one_time=False)
    for item, price in items:
        kb.add(
            Text(f"Продать {item.name} — {price} зол.", payload={"type": "sell_item", "item": item.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()
