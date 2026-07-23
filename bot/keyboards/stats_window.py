"""Клавиатура окна распределения статов в чате (патч 11, блок 1).

INLINE-клавиатура (привязана к КОНКРЕТНОМУ сообщению, не к нижней панели) —
только так можно менять кнопки через messages.edit при вложении очков.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text

STAT_ORDER = ["str", "agi", "int", "vit", "wil"]
STAT_META = {
    "str": ("💪", "Сила"),
    "agi": ("🏃", "Ловкость"),
    "int": ("🧠", "Интеллект"),
    "vit": ("❤️", "Выносливость"),
    "wil": ("✨", "Воля"),
}

BTN_CANCEL = "Отмена"
BTN_DONE = "Готово"


def stats_alloc_keyboard() -> str:
    kb = Keyboard(inline=True)
    for key in STAT_ORDER:
        emoji, _name = STAT_META[key]
        kb.add(
            Text(f"+{emoji}", payload={"type": "stat_alloc", "stat": key}),
            color=KeyboardButtonColor.SECONDARY,
        )
    kb.row()
    kb.add(Text(BTN_CANCEL, payload={"type": "stat_alloc_cancel"}), color=KeyboardButtonColor.NEGATIVE)
    kb.add(Text(BTN_DONE, payload={"type": "stat_alloc_done"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def no_keyboard() -> str:
    """Снять инлайн-кнопки с уже отредактированного сообщения (после Готово)."""
    return Keyboard(inline=True).get_json()
