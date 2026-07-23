"""Клавиатуры сцены «Раскол пути» (патч 12): выбор подкласса за золото."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

BTN_PAY = "Заплатить 20 000"
BTN_LEAVE = "Уйти"
BTN_CHOOSE_PATH = "Выбрать этот путь"
BTN_OTHER_PATH = "Другой путь"
BTN_CONFIRM_PATH = "Да, это мой путь"
BTN_THINK_MORE = "Подумаю ещё"


def offer_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_PAY), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_LEAVE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def paths_keyboard(titles: list[str]) -> str:
    kb = Keyboard(one_time=True)
    for title in titles:
        kb.add(Text(title), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def path_view_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CHOOSE_PATH), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_OTHER_PATH), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def path_confirm_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CONFIRM_PATH), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_THINK_MORE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
