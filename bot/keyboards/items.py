"""Клавиатуры экипировки (патч 11, блок 2): окно сравнения при дропе, инвентарь.

Окна редактируются на месте (патч 13, ч.1), не плодят новых сообщений
(см. bot/handlers/combat.py::item_choice, bot/handlers/inventory.py).

Патч 37: инвентарь — отдельный ЭКРАН (bot/screens.py), клавиатура ОБЫЧНАЯ
(не inline) и заменяет городскую целиком, [← Назад] — последней кнопкой.
item_choice_keyboard — окно сравнения при дропе — остаётся INLINE: это
модальная подсказка поверх текущего экрана (бой/исследование), а не переход
на новый экран навигации, дерева экранов патча 37 не касается."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.layout import add_paired
from bot.keyboards.world import add_miniapp_button
from models import Item

BTN_EQUIP = "Надеть"
BTN_KEEP = "В инвентарь"
BTN_SELL_GEAR = "🎒 Снаряжение"  # патч 41: было "Продать снаряжение"


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

# Патч 32, баг 5 / патч 41: VK ограничивает клавиатуру 10 строками — при
# одной кнопке на предмет инвентарь без накопленного лимита у активного
# игрока рано или поздно превышал лимит и ронял messages.send/.edit целиком.
# Патч 41 меняет фикс с "жёсткий срез, остальное только в мини-аппе" на
# настоящую пагинацию (как sell_gear_detail_keyboard у скупщика) — по 2
# кнопки в ряд, никто не теряется из вида в чате.
#
# Патч 109: 10 на страницу, и постранично теперь не только кнопки, но и
# текст - список из 30+ вещей одним сообщением рано или поздно упёрся бы в
# лимит длины сообщения VK. Строк клавиатуры: 5 (вещи) + страницы + мини-апп
# + назад = 8 из 10.
INVENTORY_PAGE_SIZE = 10


def inventory_page_bounds(total: int, page: int) -> tuple[int, int]:
    """(страница, всего страниц) - страница зажата в допустимые границы."""
    total_pages = max((total + INVENTORY_PAGE_SIZE - 1) // INVENTORY_PAGE_SIZE, 1)
    return max(1, min(page, total_pages)), total_pages


def inventory_keyboard(items: list[tuple[Item, bool]], page: int = 1) -> str:
    """Список предметов инвентаря — тап по предмету открывает сравнение с
    надетым. Патч 37: [← Назад] последней кнопкой — выход из экрана в город.
    Патч 41: постранично (INVENTORY_PAGE_SIZE/стр.), по 2 кнопки в ряд."""
    page, total_pages = inventory_page_bounds(len(items), page)
    page_items = items[(page - 1) * INVENTORY_PAGE_SIZE : page * INVENTORY_PAGE_SIZE]

    kb = Keyboard(one_time=False)
    add_paired(kb, [
        (
            f"{item.name}{' (надето)' if equipped else ''}",
            KeyboardButtonColor.PRIMARY if equipped else KeyboardButtonColor.SECONDARY,
            {"type": "inventory_item", "item": item.id, "page": page},
        )
        for item, equipped in page_items
    ])

    if page > 1:
        kb.add(Text("← Стр.", payload={"type": "inventory_page", "page": page - 1}), color=KeyboardButtonColor.PRIMARY)
    if page < total_pages:
        kb.add(Text("Стр. →", payload={"type": "inventory_page", "page": page + 1}), color=KeyboardButtonColor.PRIMARY)
    if page > 1 or page < total_pages:
        kb.row()

    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "inventory_root_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def item_view_keyboard(item_id: int, equipped: bool, page: int = 1) -> str:
    """Карточка одного предмета из инвентаря: [Надеть] (если не надет уже) +
    [← Назад] к списку (патч 13, ч.1 — одно редактируемое окно на весь просмотр).
    Отдельный payload от item_choice (окно сравнения при дропе) — тут нет
    pending-состояния, надеть можно любой лежащий в инвентаре предмет."""
    kb = Keyboard(one_time=False)
    if not equipped:
        kb.add(
            Text(BTN_EQUIP, payload={"type": "inventory_equip", "item": item_id, "page": page}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "inventory_back", "page": page}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
