"""Клавиатуры открытого PvP (патч 22): выбор стороны при вступлении в чужой
бой + боевая клавиатура дуэли/массового боя (БЕЗ побега — нападение
принудительное, отказаться от уже идущего боя нельзя).

ВАЖНО: текст/payload кнопок намеренно ОТЛИЧАЮТСЯ от PvE-боевых (BTN_ATTACK /
payload {"type":"skill"} из bot/handlers/combat.py) — vkbottle диспетчерит
по ПЕРВОМУ зарегистрированному обработчику с совпадающим правилом и на этом
останавливается (blocking=True по умолчанию), поэтому одинаковый текст/payload
у двух разных лейблеров означал бы, что PvP-обработчик никогда не вызовется
(PvE-обработчик комбата всегда бы «перехватывал» нажатие первым)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.combat.base_skills import skills_for_class

BTN_PVP_ATTACK = "🗡️ Атаковать"


def join_side_keyboard(session_id: int) -> str:
    """«К кому присоединиться?» — инлайн-кнопки 1/2 (payload) вдобавок к тому,
    что можно и просто написать «1» или «2» текстом (см. bot/handlers/pvp.py)."""
    kb = Keyboard(inline=True)
    for side in (1, 2):
        kb.add(
            Text(str(side), payload={"type": "pvp_join", "session_id": session_id, "side": side}),
            color=KeyboardButtonColor.SECONDARY,
        )
    return kb.get_json()


def pvp_combat_keyboard(base_class: str, cooldowns: dict[str, int]) -> str:
    """Как combat_keyboard (PvE), но БЕЗ побега и БЕЗ зелий (патч 22 — только
    встреча/нападение/ставки/массовые бои; открытое PvP: бой навязан,
    сбежать из уже идущей встречи нельзя)."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_PVP_ATTACK), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    for skill in skills_for_class(base_class):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        kb.add(Text(label, payload={"type": "pvp_skill", "id": skill.id}), color=color)
        kb.row()
    return kb.get_json()


def pvp_waiting_keyboard() -> str:
    """Между ходами массового боя (ждём таймер/остальных) — без кнопок боя,
    но с мини-аппом, как и в PvE-ожидании."""
    kb = Keyboard(one_time=False)
    add_miniapp_button(kb)
    return kb.get_json()
