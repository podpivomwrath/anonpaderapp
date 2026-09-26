"""Кнопка захода к мировому боссу (патч 104).

Инлайн отдельным сообщением, как у рудника и озера: в клавиатуре перемещения
места нет (bot/keyboards/layout.py)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.world_boss_texts import BTN_ATTACK


def attack_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_ATTACK, payload={"type": "world_boss_attack"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
