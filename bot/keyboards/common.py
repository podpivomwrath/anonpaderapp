"""VK-клавиатуры. Пока заглушка: одно главное меню.

TODO: клавиатуры боя (выбор действия на тик), инвентаря, биржи.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text


def main_menu_keyboard() -> str:
    kb = Keyboard(one_time=False, inline=False)
    kb.add(Text("Профиль"), color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()
