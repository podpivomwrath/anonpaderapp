"""Клавиатуры скупщика: трофеи (патч 9) + снаряжение (патч 11, блок 2; патч 35 —
группировка снаряжения по редкости + подробный режим с пагинацией).

Общее правило (патч 35): любой список в чате, длина которого зависит от
данных игрока (инвентарь, трофеи, маунты, пресеты, репорты, игроки на
клетке), обязан быть сгруппирован или разбит на страницы — нельзя выводить
по кнопке на элемент, иначе рост количества рано или поздно упрётся в лимит
клавиатуры VK (10 строк) и сломает экран целиком."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import ItemRarityDef, TrophyDef
from models import Item

SELL_ALL_ID = "all"
BTN_SELL_GEAR = "🗡️ Продать снаряжение"
BTN_GEAR_DETAIL = "📋 По предметам"
BTN_BACK = "← Назад"

# Патч 35: 6 предметов на страницу подробного режима — вместе с двумя
# служебными строками (пагинация + назад) и кнопкой мини-аппа укладывается
# в лимит VK (10 строк) при любом размере инвентаря.
GEAR_DETAIL_PAGE_SIZE = 6


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


def sell_gear_main_keyboard(
    groups: list[tuple[ItemRarityDef, list[Item], int]], grand_total: int
) -> str:
    """Основной экран продажи снаряжения (патч 35) — до 5 кнопок продажи (по
    одной на присутствующую редкость) + «Продать всё» + подробный режим +
    назад, вместо одной кнопки на предмет."""
    kb = Keyboard(inline=True)
    if groups:
        kb.add(
            Text(f"Продать всё — {grand_total} зол.", payload={"type": "sell_all_gear"}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
        for rdef, items, total in groups:
            label = f"Продать {rdef.emoji} ×{len(items)} — {total} зол."
            kb.add(
                Text(label, payload={"type": "sell_rarity", "rarity": rdef.id}),
                color=KeyboardButtonColor.SECONDARY,
            )
            kb.row()
        kb.add(Text(BTN_GEAR_DETAIL, payload={"type": "gear_detail", "page": 1}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "gear_back"}), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def sell_gear_detail_keyboard(page_items: list[Item], page: int, total_pages: int) -> str:
    """Подробный режим (патч 35): нумерованные кнопки продажи по позиции на
    странице + пагинация + назад к основному экрану."""
    kb = Keyboard(inline=True)
    for i, item in enumerate(page_items, start=1):
        kb.add(Text(str(i), payload={"type": "sell_item", "item": item.id, "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    if page > 1:
        kb.add(Text("← Стр.", payload={"type": "gear_detail", "page": page - 1}), color=KeyboardButtonColor.PRIMARY)
    if page < total_pages:
        kb.add(Text("Стр. →", payload={"type": "gear_detail", "page": page + 1}), color=KeyboardButtonColor.PRIMARY)
    if page > 1 or page < total_pages:
        kb.row()

    kb.add(Text(BTN_BACK, payload={"type": "gear_back_main"}), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def sell_confirm_keyboard(confirm_payload: dict) -> str:
    """Предупреждение «в группе есть предмет лучше надетого» (патч 35): явное
    подтверждение вместо мгновенной продажи."""
    kb = Keyboard(inline=True)
    kb.add(Text("Да, продать", payload=confirm_payload), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("Отмена", payload={"type": "gear_back_main"}), color=KeyboardButtonColor.NEGATIVE)
    add_miniapp_button(kb)
    return kb.get_json()
