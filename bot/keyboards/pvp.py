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

from bot.keyboards.layout import add_paired
from bot.keyboards.world import add_miniapp_button
from game.combat.base_skills import skills_for_character
from game.content_loader import ElixirDef

# Патч 41: сколько целей помещается в один ряд инлайн-клавиатуры выбора цели
# без переполнения экрана — свыше этого пришлось бы пагинировать.
_TARGET_ROW_WIDTH = 5

BTN_PVP_ATTACK = "🗡️ Атаковать"
# Патч 30, баг 3, п.3: у PvE "🎒 Предмет" (bot/keyboards/world.py) — намеренно
# ДРУГОЙ текст здесь же, по той же причине, что и BTN_PVP_ATTACK выше.
BTN_PVP_ITEM = "🎒 Предметы"
BTN_PVP_TARGET = "🎯 Цель"  # патч 38 — только массовый PvP, не дуэль (см. show_target)


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


def pvp_combat_keyboard(
    base_class: str, cooldowns: dict[str, int], show_target: bool = False,
    subclass_id: str | None = None,
) -> str:
    """Как combat_keyboard (PvE), но БЕЗ побега (патч 22 — бой навязан,
    сбежать из уже идущей встречи нельзя). Патч 30: предметы ДОБАВЛЕНЫ —
    раньше их не было вовсе, хотя патч 16 (зелья/эликсиры) не делал для
    PvP исключения. show_target (патч 38) — кнопка [🎯 Цель] только для
    массового боя (2+ противников есть смысл выбирать); в дуэли 1×1
    противник ровно один, выбор не нужен. subclass_id (патч 39, ч.3) —
    после выбора подкласса навыки класса ЗАМЕНЯЮТСЯ навыками подкласса.

    Патч 41: 2 колонки — та же раскладка, что у PvE combat_keyboard."""
    kb = Keyboard(one_time=False)
    items: list[tuple[str, KeyboardButtonColor, dict | None]] = [
        (BTN_PVP_ATTACK, KeyboardButtonColor.POSITIVE, None)
    ]
    for skill in skills_for_character(base_class, subclass_id):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        items.append((label, color, {"type": "pvp_skill", "id": skill.id}))
    if show_target:
        items.append((BTN_PVP_TARGET, KeyboardButtonColor.SECONDARY, None))
    items.append((BTN_PVP_ITEM, KeyboardButtonColor.SECONDARY, None))
    add_paired(kb, items)
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


def pvp_target_keyboard(enemy_ids: list[int]) -> str:
    """Выбор цели в массовом PvP (патч 38) — по кнопке на противника
    (нумерация как в тексте списка) + [← Назад] последней строкой (по
    форме экранов патча 37 — сам character.screen сюда не подключаем: бой
    уже подчиняется отдельному правилу приоритета боевой клавиатуры, см.
    services/screen_service.py и docstring bot/handlers/world.py::_current_keyboard).
    Инлайн и через editable_message — как и pvp_items_keyboard выше, тот же
    приём "временная подпанель поверх боевой клавиатуры", не отдельный экран.

    Патч 41: цели переносятся по _TARGET_ROW_WIDTH в ряд — при 5+ противниках
    список раньше растягивался в одну длинную строку."""
    kb = Keyboard(inline=True)
    for i, cid in enumerate(enemy_ids, start=1):
        kb.add(Text(str(i), payload={"type": "pvp_target_pick", "target": cid}), color=KeyboardButtonColor.SECONDARY)
        if i % _TARGET_ROW_WIDTH == 0:
            kb.row()
    if len(enemy_ids) % _TARGET_ROW_WIDTH != 0:
        kb.row()
    kb.add(Text("← Назад", payload={"type": "pvp_target_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def pvp_waiting_keyboard() -> str:
    """Между ходами массового боя (ждём таймер/остальных) — без кнопок боя,
    но с мини-аппом, как и в PvE-ожидании."""
    kb = Keyboard(one_time=False)
    add_miniapp_button(kb)
    return kb.get_json()
