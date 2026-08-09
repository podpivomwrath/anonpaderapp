"""Клавиатуры скупщика: трофеи (патч 9) + снаряжение (патч 11, блок 2; патч 35 —
группировка снаряжения по редкости + подробный режим с пагинацией).

Патч 37: скупщик — ДЕРЕВО экранов (bot/screens.py), не одно окно с накопленными
инлайн-кнопками поверх городской клавиатуры. Каждый экран — своя ОБЫЧНАЯ
(не inline) клавиатура, которая ЦЕЛИКОМ заменяет предыдущую (в т.ч. городскую)
на панели внизу — раньше городская клавиатура так и оставалась висеть, а
инлайн-кнопки скупщика добавлялись поверх неё, что и ломало экран при
достаточном числе кнопок. [← Назад] — всегда ПОСЛЕДНЯЯ кнопка экрана.

Дерево: Город → Скупщик (root, 2 кнопки) → {Продать трофеи | Продать
снаряжение → По предметам (пагинация)}.

Общее правило (патч 35/37): любой список в чате, длина которого зависит от
данных игрока, обязан быть сгруппирован или разбит на страницы — нельзя
выводить по кнопке на элемент, иначе рост количества упрётся в лимит
клавиатуры VK и сломает экран."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import ItemRarityDef, TrophyDef
from models import Item

SELL_ALL_ID = "all"
BTN_TROPHIES = "🧿 Продать трофеи"
BTN_SELL_GEAR = "🗡 Продать снаряжение"
BTN_GEAR_DETAIL = "📋 По предметам"
BTN_BACK = "← Назад"

# Патч 35: 6 предметов на страницу подробного режима — вместе со служебными
# строками (пагинация + миниапп + назад) укладывается в лимит VK (10 строк)
# при любом размере инвентаря.
GEAR_DETAIL_PAGE_SIZE = 6


def no_keyboard() -> str:
    """Снять клавиатуру с уже отредактированного сообщения (окно закрыто)."""
    return Keyboard(inline=True).get_json()


def appraiser_root_keyboard() -> str:
    """Патч 37: корневой экран скупщика — всего 2 действия + назад, вместо
    того чтобы сразу вываливать список трофеев поверх городской клавиатуры."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_TROPHIES, payload={"type": "appraiser_trophies"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_SELL_GEAR, payload={"type": "appraiser_gear"}), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def appraiser_trophies_keyboard(stock: list[tuple[TrophyDef, int]]) -> str:
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
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_root"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def sell_gear_main_keyboard(
    groups: list[tuple[ItemRarityDef, list[Item], int]], grand_total: int
) -> str:
    """Основной экран продажи снаряжения (патч 35/37) — до 5 кнопок продажи (по
    одной на присутствующую редкость) + «Продать всё» + подробный режим +
    назад, вместо одной кнопки на предмет и вместо инлайн-наложения на город."""
    kb = Keyboard(one_time=False)
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
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_root"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def sell_gear_detail_keyboard(page_items: list[Item], page: int, total_pages: int) -> str:
    """Подробный режим (патч 35/37): нумерованные кнопки продажи по позиции на
    странице + пагинация + назад к основному экрану снаряжения."""
    kb = Keyboard(one_time=False)
    for i, item in enumerate(page_items, start=1):
        kb.add(Text(str(i), payload={"type": "sell_item", "item": item.id, "page": page}), color=KeyboardButtonColor.SECONDARY)
        kb.row()

    if page > 1:
        kb.add(Text("← Стр.", payload={"type": "gear_detail", "page": page - 1}), color=KeyboardButtonColor.PRIMARY)
    if page < total_pages:
        kb.add(Text("Стр. →", payload={"type": "gear_detail", "page": page + 1}), color=KeyboardButtonColor.PRIMARY)
    if page > 1 or page < total_pages:
        kb.row()

    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_gear"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def sell_confirm_keyboard(confirm_payload: dict) -> str:
    """Предупреждение «в группе есть предмет лучше надетого» (патч 35): явное
    подтверждение вместо мгновенной продажи. Отмена — назад к экрану снаряжения."""
    kb = Keyboard(one_time=False)
    kb.add(Text("Да, продать", payload=confirm_payload), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text("Отмена", payload={"type": "appraiser_gear"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
