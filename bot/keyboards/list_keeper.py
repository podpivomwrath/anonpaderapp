"""Клавиатуры сцены «Раскол пути» (патч 12): выбор подкласса за золото."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

BTN_PAY = "Заплатить 20 000"
BTN_LEAVE = "Уйти"
BTN_CHOOSE_PATH = "Выбрать этот путь"
BTN_OTHER_PATH = "Другой путь"
BTN_CONFIRM_PATH = "Да, это мой путь"
BTN_THINK_MORE = "Подумаю ещё"

# Переделка персонажа (альфа-тест): Хранитель переписывает запись в Списке.
BTN_REMAKE = "Переделать себя"
BTN_REMAKE_CLASS = "Сменить класс"
BTN_REMAKE_SUBCLASS = "Сменить подкласс"
BTN_REMAKE_STATS = "Сбросить характеристики"
BTN_REMAKE_CANCEL = "Оставить как есть"
BTN_REMAKE_CONFIRM = "Да, переделать"
BTN_KEEPER_LEAVE = "Уйти в таверну"


def offer_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_PAY), color=KeyboardButtonColor.POSITIVE)
    kb.row()
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
    kb.row()
    kb.add(Text(BTN_OTHER_PATH), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def path_confirm_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CONFIRM_PATH), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text(BTN_THINK_MORE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def remake_keyboard(has_subclass: bool) -> str:
    """Меню переделки. Пункт «Сменить подкласс» показывается только тому, у
    кого подкласс есть - иначе он ведёт в никуда."""
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_REMAKE_CLASS), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    if has_subclass:
        kb.add(Text(BTN_REMAKE_SUBCLASS), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    kb.add(Text(BTN_REMAKE_STATS), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text(BTN_REMAKE_CANCEL), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def remake_confirm_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_REMAKE_CONFIRM), color=KeyboardButtonColor.NEGATIVE)
    kb.row()
    kb.add(Text(BTN_REMAKE_CANCEL), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def base_class_keyboard(titles: list[str]) -> str:
    kb = Keyboard(one_time=True)
    for title in titles:
        kb.add(Text(title), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    kb.add(Text(BTN_REMAKE_CANCEL), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def trials_keyboard() -> str:
    """Окно испытаний: отсюда же можно переписать запись в Списке."""
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_REMAKE), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_KEEPER_LEAVE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
