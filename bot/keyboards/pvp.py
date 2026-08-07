"""Клавиатуры открытого PvP (патч 22): выбор стороны при вступлении в чужой
бой + боевая клавиатура дуэли/массового боя (БЕЗ побега — нападение
принудительное, отказаться от уже идущего боя нельзя; патч 30 добавил
предметы — зелья/эликсиры работают в PvP по тем же правилам, что в PvE).

ВАЖНО: текст/payload кнопок намеренно ОТЛИЧАЮТСЯ от PvE-боевых (BTN_ATTACK /
payload {"type":"skill"} из bot/handlers/combat.py) — vkbottle диспетчерит
по ПЕРВОМУ зарегистрированному обработчику с совпадающим правилом и на этом
останавливается (blocking=True по умолчанию), поэтому одинаковый текст/payload
у двух разных лейблеров означал бы, что PvP-обработчик никогда не вызовется
(PvE-обработчик комбата всегда бы «перехватывал» нажатие первым)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.combat.base_skills import skills_for_class
from game.content_loader import ElixirDef

BTN_PVP_ATTACK = "🗡️ Атаковать"
# Патч 30, баг 3, п.3: у PvE "🎒 Предмет" (bot/keyboards/world.py) — намеренно
# ДРУГОЙ текст здесь же, по той же причине, что и BTN_PVP_ATTACK выше.
BTN_PVP_ITEM = "🎒 Предметы"


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
    """Как combat_keyboard (PvE), но БЕЗ побега (патч 22 — бой навязан,
    сбежать из уже идущей встречи нельзя). Патч 30: предметы ДОБАВЛЕНЫ —
    раньше их не было вовсе, хотя патч 16 (зелья/эликсиры) не делал для
    PvP исключения."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_PVP_ATTACK), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    for skill in skills_for_class(base_class):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        kb.add(Text(label, payload={"type": "pvp_skill", "id": skill.id}), color=color)
        kb.row()
    kb.add(Text(BTN_PVP_ITEM), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def pvp_items_keyboard(stock: list[tuple[ElixirDef, int]]) -> str:
    """Список зелий/эликсиров в PvP-бою (патч 30) — payload {"type":
    "pvp_use_item"}, НАМЕРЕННО отличный от PvE {"type":"use_item"}
    (bot/keyboards/combat_items.py) по той же причине, что и BTN_PVP_ATTACK."""
    kb = Keyboard(inline=True)
    for idx, (elixir, count) in enumerate(stock):
        label = f"{elixir.emoji} {elixir.name} ×{count}"
        kb.add(
            Text(label, payload={"type": "pvp_use_item", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if idx % 2 == 1:
            kb.row()
    if len(stock) % 2 == 1:
        kb.row()
    return kb.get_json()


def pvp_waiting_keyboard() -> str:
    """Между ходами массового боя (ждём таймер/остальных) — без кнопок боя,
    но с мини-аппом, как и в PvE-ожидании."""
    kb = Keyboard(one_time=False)
    add_miniapp_button(kb)
    return kb.get_json()
