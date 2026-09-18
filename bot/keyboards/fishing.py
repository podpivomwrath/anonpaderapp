"""Клавиатуры рыбалки (патч 58).

Экран озера — вложенный (services/screen_service.py), поэтому он заменяет
клавиатуру ЦЕЛИКОМ и обязан иметь выход. Родитель у него корневой: озеро
стоит на карте, а не в городе.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.fishing_texts import BTN_BAG, BTN_CAST, BTN_FISH, BTN_LEAVE_LAKE, BTN_STRIKE


def lake_keyboard() -> str:
    """Стоим у воды, снасть не заброшена."""
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CAST), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text(BTN_BAG), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_LEAVE_LAKE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def casting_keyboard() -> str:
    """Снасть в воде, поклёвки ещё не было. Кнопки подсечки здесь НЕТ: она
    появляется только вместе с сообщением о поклёвке (bite_keyboard ниже).

    Так подсечка и становится подсечкой — реакцией на событие, а не кнопкой,
    которую можно нажать заранее и ждать. Сообщение о поклёвке присылает
    планировщик (bot/handlers/fishing.py::_on_bite)."""
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_LEAVE_LAKE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def bite_keyboard() -> str:
    """Клюёт! Приходит ОТДЕЛЬНЫМ сообщением в момент поклёвки; окно на
    подсечку — fishing_config.STRIKE_WINDOW_SECONDS."""
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_STRIKE), color=KeyboardButtonColor.PRIMARY)
    kb.row()
    kb.add(Text(BTN_LEAVE_LAKE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def bag_keyboard() -> str:
    kb = Keyboard(one_time=True)
    kb.add(Text(BTN_CAST), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    kb.add(Text(BTN_LEAVE_LAKE), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def approach_lake_keyboard() -> str:
    """Кнопка «К воде» ОТДЕЛЬНЫМ сообщением с ИНЛАЙН-клавиатурой — ровно как
    «Прикоснуться» у Монолита (bot/keyboards/raid.py).

    В клавиатуру перемещения её класть нельзя: там уже 7 рядов (крест, отдых,
    осмотреться, маунт, горстка пепла, мини-апп), и восьмая кнопка нарушила бы
    правило из bot/keyboards/layout.py про 6 кнопок на экран. Инлайн-клавиатура
    живёт на своём сообщении и нижнюю reply-клавиатуру карты не трогает.
    """
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_FISH, payload={"type": "approach_lake"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()
