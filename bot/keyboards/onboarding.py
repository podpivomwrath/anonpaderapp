"""Клавиатуры сцен онбординга."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.onboarding_texts import (
    BTN_BEGIN,
    BTN_CHOOSE_PATH,
    BTN_CONFIRM_PATH,
    BTN_GO_REGION,
    BTN_OTHER_PATHS,
    BTN_OTHER_ROADS,
    BTN_THINK_MORE,
    BTN_YES,
    CLASS_BUTTONS,
    REGION_BUTTONS,
)


def empty_keyboard() -> str:
    """Убирает клавиатуру (ожидание текстового ввода)."""
    return Keyboard().get_json()


def classes_keyboard() -> str:
    kb = Keyboard(one_time=True)
    for label in CLASS_BUTTONS:
        kb.add(Text(label), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def path_view_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CHOOSE_PATH), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_OTHER_PATHS), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def path_confirm_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CONFIRM_PATH), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_THINK_MORE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def regions_keyboard() -> str:
    kb = Keyboard(one_time=True)
    for i, label in enumerate(REGION_BUTTONS):
        if i == 2:
            kb.row()
        kb.add(Text(label), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def region_view_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_GO_REGION), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_OTHER_ROADS), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def region_confirm_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_YES), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_THINK_MORE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def begin_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_BEGIN), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()
