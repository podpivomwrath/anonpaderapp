"""Арена (2026-10-18): тренировочные бои игроков в городе."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

BTN_ARENA_RANDOM = "🎲 Случайный бой"
BTN_ARENA_HOST = "⏳ Ждать соперника"
BTN_ARENA_FIND = "🔎 Найти по коду"
BTN_ARENA_FIND_OLD = "🔎 Найти соперника"  # у кого клавиатура старая
BTN_ARENA_CANCEL = "✖ Отменить"
BTN_ARENA_BACK = "← Таверна"
# Комната массового боя (2026-10-29, владелец).
BTN_ROOM_CREATE = "👥 Комната на бой"
BTN_ROOM_SIDE_1 = "🔴 Сторона 1"
BTN_ROOM_SIDE_2 = "🔵 Сторона 2"
BTN_ROOM_START = "▶ Начать бой"
BTN_ROOM_LEAVE = "✖ Выйти из комнаты"


def arena_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ARENA_RANDOM), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_ROOM_CREATE), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text(BTN_ARENA_HOST), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text(BTN_ARENA_FIND), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text(BTN_ARENA_BACK), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def arena_waiting_keyboard() -> str:
    """В очереди, с кодом или при вводе кода - только отмена."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ARENA_CANCEL), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def room_keyboard(is_host: bool) -> str:
    """В комнате: выбор стороны, у хозяина ещё «Начать бой»."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ROOM_SIDE_1), color=KeyboardButtonColor.NEGATIVE)
    kb.add(Text(BTN_ROOM_SIDE_2), color=KeyboardButtonColor.PRIMARY)
    if is_host:
        kb.row()
        kb.add(Text(BTN_ROOM_START), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text(BTN_ROOM_LEAVE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
