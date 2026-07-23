"""Клавиатуры экипировки (патч 11, блок 2): окно сравнения при дропе, инвентарь."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from models import Item

BTN_EQUIP = "Надеть"
BTN_KEEP = "В инвентарь"
BTN_SELL_GEAR = "🎒 Продать снаряжение"


def item_choice_keyboard(item_id: int) -> str:
    """[Надеть] / [В инвентарь] — окно сравнения после дропа предмета."""
    kb = Keyboard(one_time=False)
    kb.add(
        Text(BTN_EQUIP, payload={"type": "item_choice", "action": "equip", "item": item_id}),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    kb.add(
        Text(BTN_KEEP, payload={"type": "item_choice", "action": "keep", "item": item_id}),
        color=KeyboardButtonColor.SECONDARY,
    )
    add_miniapp_button(kb)
    return kb.get_json()


def inventory_keyboard(items: list[tuple[Item, bool]]) -> str:
    """Список предметов инвентаря — тап по предмету открывает сравнение с надетым."""
    kb = Keyboard(one_time=False)
    for item, equipped in items:
        label = f"{item.name}{' (надето)' if equipped else ''}"
        kb.add(
            Text(label, payload={"type": "inventory_item", "item": item.id}),
            color=KeyboardButtonColor.PRIMARY if equipped else KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()


def item_view_keyboard(item_id: int, equipped: bool) -> str:
    """Карточка одного предмета из инвентаря: [Надеть] (если не надет уже).
    Отдельный payload от item_choice (окно сравнения при дропе) — тут нет
    pending-состояния, надеть можно любой лежащий в инвентаре предмет."""
    kb = Keyboard(one_time=False)
    if not equipped:
        kb.add(
            Text(BTN_EQUIP, payload={"type": "inventory_equip", "item": item_id}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()
