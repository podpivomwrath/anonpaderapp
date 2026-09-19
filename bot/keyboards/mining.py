"""Клавиатуры горного дела (патч 59).

Экран рудника — вложенный (services/screen_service.py), родитель корневой:
рудник стоит на карте, а не в городе. Правило bot/keyboards/layout.py про
6 кнопок на экран соблюдается с запасом — здесь их максимум три.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.mining_texts import (
    BTN_ABANDON,
    BTN_DIG,
    BTN_DIG_VEIN,
    BTN_LEAVE_MINE,
    BTN_MINE,
    BTN_ORE,
)


def mine_keyboard(has_ore: bool) -> str:
    """Стоим в выработке, кирка не в деле.

    has_ore=False — жила пуста, кнопку добычи не показываем вовсе: предлагать
    действие, которое гарантированно откажет, хуже, чем не предлагать.
    """
    kb = Keyboard(one_time=True)
    if has_ore:
        kb.add(Text(BTN_DIG), color=KeyboardButtonColor.POSITIVE)
        kb.row()
    kb.add(Text(BTN_ORE), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_LEAVE_MINE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def digging_keyboard() -> str:
    """Идёт добыча. Действий ровно два, и оба — выход из неё: добыча блокирует
    всё остальное, и показывать кнопки, которые всё равно откажут, незачем.

    «Выйти наверх» у статичного рудника сохраняет остаток времени (вернёшься и
    доработаешь, пока не ушёл с клетки), «Бросить кирку» отменяет добычу
    насовсем вместе с уже отбитой породой.
    """
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_LEAVE_MINE), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_ABANDON), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def ore_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_LEAVE_MINE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def approach_mine_keyboard() -> str:
    """Кнопка «В выработку» отдельным сообщением с ИНЛАЙН-клавиатурой — как у
    Монолита и озера. В клавиатуру перемещения её класть нельзя: там уже семь
    рядов, и правило про 6 кнопок на экран было бы нарушено."""
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_MINE, payload={"type": "approach_mine"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def event_vein_keyboard(event_id: str) -> str:
    """Мелкая жила в исследовании: добыча начинается прямо из события, своего
    экрана у неё нет — она исчезает при любом выходе."""
    kb = Keyboard(inline=True)
    kb.add(
        Text(BTN_DIG_VEIN, payload={"type": "dig_vein", "event": event_id}),
        color=KeyboardButtonColor.POSITIVE,
    )
    return kb.get_json()
