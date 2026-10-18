"""Арена (2026-10-18): тренировочные бои игроков в городе."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

BTN_ARENA_RANDOM = "🎲 Случайный бой"
BTN_ARENA_HOST = "⏳ Ждать соперника"
BTN_ARENA_FIND = "🔎 Найти соперника"
BTN_ARENA_CANCEL = "✖ Отменить"
BTN_ARENA_BACK = "← Таверна"


def arena_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ARENA_RANDOM), color=KeyboardButtonColor.POSITIVE)
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
