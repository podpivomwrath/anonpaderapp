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

from bot.keyboards.layout import add_paired
from bot.keyboards.world import add_miniapp_button
from game.content_loader import ItemRarityDef, TrophyDef
from models import Item

SELL_ALL_ID = "all"
BTN_TROPHIES = "🧿 Трофеи"  # патч 41: было "Продать трофеи"
BTN_SELL_GEAR = "🗡 Снаряжение"  # патч 41: было "Продать снаряжение"
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
    того чтобы сразу вываливать список трофеев поверх городской клавиатуры.
    Патч 41: 2 действия — уже одна строка при паре."""
    kb = Keyboard(one_time=False)
    add_paired(kb, [
        (BTN_TROPHIES, KeyboardButtonColor.SECONDARY, {"type": "appraiser_trophies"}),
        (BTN_SELL_GEAR, KeyboardButtonColor.SECONDARY, {"type": "appraiser_gear"}),
    ])
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def appraiser_trophies_keyboard(stock: list[tuple[TrophyDef, int]]) -> str:
    """Патч 41: «Продать всё» — во всю ширину (главное действие), остальные
    градации трофеев — по 2 в ряд."""
    kb = Keyboard(one_time=False)
    if stock:
        total = sum(d.sell_price * count for d, count in stock)
        kb.add(
            Text(f"Продать всё — {total} зол.", payload={"type": "sell_trophies", "id": SELL_ALL_ID}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
        items = [
            (f"Продать {trophy_def.emoji} ×{count} — {price} зол.", KeyboardButtonColor.SECONDARY,
             {"type": "sell_trophies", "id": trophy_def.id})
            for trophy_def, count in stock
            for price in [trophy_def.sell_price * count]
        ]
        add_paired(kb, items)
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_root"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def sell_gear_main_keyboard(
    groups: list[tuple[ItemRarityDef, list[Item], int]], grand_total: int
) -> str:
    """Основной экран продажи снаряжения (патч 35/37) — до 5 кнопок продажи (по
    одной на присутствующую редкость) + «Продать всё» + подробный режим +
    назад, вместо одной кнопки на предмет и вместо инлайн-наложения на город.
    Патч 41: редкости — по 2 в ряд, «Продать всё» остаётся главным действием."""
    kb = Keyboard(one_time=False)
    if groups:
        kb.add(
            Text(f"Продать всё — {grand_total} зол.", payload={"type": "sell_all_gear"}),
            color=KeyboardButtonColor.POSITIVE,
        )
        kb.row()
        items = [
            (f"Продать {rdef.emoji} ×{len(items_)} — {total} зол.", KeyboardButtonColor.SECONDARY,
             {"type": "sell_rarity", "rarity": rdef.id})
            for rdef, items_, total in groups
        ]
        items.append((BTN_GEAR_DETAIL, KeyboardButtonColor.SECONDARY, {"type": "gear_detail", "page": 1}))
        add_paired(kb, items)
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "appraiser_root"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def sell_gear_detail_keyboard(page_items: list[Item], page: int, total_pages: int) -> str:
    """Подробный режим (патч 35/37): нумерованные кнопки продажи по позиции на
    странице + пагинация + назад к основному экрану снаряжения.
    Патч 41: позиции — по 2 в ряд вместо столбика."""
    kb = Keyboard(one_time=False)
    add_paired(kb, [
        (str(i), KeyboardButtonColor.SECONDARY, {"type": "sell_item", "item": item.id, "page": page})
        for i, item in enumerate(page_items, start=1)
    ])

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
