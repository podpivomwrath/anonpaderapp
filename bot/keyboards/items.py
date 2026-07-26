"""Клавиатуры экипировки (патч 11, блок 2): окно сравнения при дропе, инвентарь.

INLINE (патч 13, ч.1) — все три окна редактируются на месте, не плодят новых
сообщений (см. bot/handlers/combat.py::item_choice, bot/handlers/inventory.py)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from models import Item

BTN_EQUIP = "Надеть"
BTN_KEEP = "В инвентарь"
BTN_SELL_GEAR = "🎒 Продать снаряжение"


def no_keyboard() -> str:
    """Снять инлайн-кнопки с уже отредактированного сообщения (окно закрыто)."""
    return Keyboard(inline=True).get_json()


def item_choice_keyboard(item_id: int) -> str:
    """[Надеть] / [В инвентарь] — окно сравнения после дропа предмета."""
    kb = Keyboard(inline=True)
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


BTN_BACK = "← Назад"


def inventory_keyboard(items: list[tuple[Item, bool]]) -> str:
    """Список предметов инвентаря — тап по предмету открывает сравнение с надетым."""
    kb = Keyboard(inline=True)
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
    """Карточка одного предмета из инвентаря: [Надеть] (если не надет уже) +
    [← Назад] к списку (патч 13, ч.1 — одно редактируемое окно на весь просмотр).
    Отдельный payload от item_choice (окно сравнения при дропе) — тут нет
    pending-состояния, надеть можно любой лежащий в инвентаре предмет."""
    kb = Keyboard(inline=True)
    if not equipped:
        kb.add(
            Text(BTN_EQUIP, payload={"type": "inventory_equip", "item": item_id}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "inventory_back"}), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()
