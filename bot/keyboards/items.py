"""Клавиатуры экипировки (патч 11, блок 2): окно сравнения при дропе, инвентарь.

Окна редактируются на месте (патч 13, ч.1), не плодят новых сообщений
(см. bot/handlers/combat.py::item_choice, bot/handlers/inventory.py).

Патч 37: инвентарь — отдельный ЭКРАН (bot/screens.py), клавиатура ОБЫЧНАЯ
(не inline) и заменяет городскую целиком, [← Назад] — последней кнопкой.
item_choice_keyboard — окно сравнения при дропе — остаётся INLINE: это
модальная подсказка поверх текущего экрана (бой/исследование), а не переход
на новый экран навигации, дерева экранов патча 37 не касается."""

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

# Патч 32, баг 5: VK ограничивает клавиатуру 10 строками — при одной кнопке
# на предмет инвентарь без накопленного лимита у активного игрока (трофеи не
# продаются автоматически, предметы просто копятся) рано или поздно превышал
# лимит, VK отклонял messages.send/.edit целиком, и кнопка «Инвентарь» на
# вид работала (сообщение с клавиатурой уже было показано раньше), а на
# нажатие переставала отвечать вовсе — ошибка API падала за пределами
# перехватываемого в editable_message.send_or_edit. Одна строка остаётся под
# кнопку мини-аппа (add_miniapp_button ниже), где полный список без лимита.
INVENTORY_KEYBOARD_MAX_ITEMS = 9


def inventory_keyboard(items: list[tuple[Item, bool]]) -> str:
    """Список предметов инвентаря — тап по предмету открывает сравнение с
    надетым. Патч 37: [← Назад] последней кнопкой — выход из экрана в город."""
    kb = Keyboard(one_time=False)
    for item, equipped in items[:INVENTORY_KEYBOARD_MAX_ITEMS]:
        label = f"{item.name}{' (надето)' if equipped else ''}"
        kb.add(
            Text(label, payload={"type": "inventory_item", "item": item.id}),
            color=KeyboardButtonColor.PRIMARY if equipped else KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "inventory_root_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def item_view_keyboard(item_id: int, equipped: bool) -> str:
    """Карточка одного предмета из инвентаря: [Надеть] (если не надет уже) +
    [← Назад] к списку (патч 13, ч.1 — одно редактируемое окно на весь просмотр).
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
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "inventory_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
