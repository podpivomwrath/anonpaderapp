"""Клавиатуры рейда «Кукольный театр» (патч 53).

payload-типы НАМЕРЕННО отличаются от group_pve_*/pvp_*/skill (см. докстринг
bot/keyboards/group_combat.py — vkbottle диспетчерит по первому совпавшему
правилу, совпадающий payload у двух лейблеров означал бы, что один
обработчик никогда не вызовется)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards import combat_modes
from bot.keyboards.layout import add_paired
from bot.raid_texts import BTN_PUPPET_THEATRE, BTN_RAID_BACK, BTN_RAID_CANCEL_READY, BTN_TOUCH_MONOLITH
from game.combat.base_skills import skills_for_character

_TARGET_ROW_WIDTH = 5
_RAID = combat_modes.RAID

# Публичные имена подписей рейда — чтобы обработчики (bot/handlers/
# raid_combat.py) ссылались на константу, а не на строковый литерал.
BTN_RAID_ATTACK = _RAID.attack
BTN_RAID_ITEM = _RAID.item
BTN_RAID_TARGET = _RAID.target


def touch_monolith_keyboard() -> str:
    """Инлайн-кнопка, прикреплённая К СООБЩЕНИЮ сводки локации (0;0) — НЕ
    заменяет нижнюю (reply) клавиатуру перемещения, которая остаётся снизу
    от предыдущего сообщения (см. bot/handlers/world.py)."""
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_TOUCH_MONOLITH, payload={"type": "raid_touch"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


def raid_list_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_PUPPET_THEATRE, payload={"type": "raid_pick", "raid": "puppet_theatre"}))
    kb.row()
    kb.add(Text(BTN_RAID_BACK, payload={"type": "raid_list_back"}))
    return kb.get_json()


def raid_lobby_keyboard(ready: bool = True) -> str:
    kb = Keyboard(inline=True)
    if ready:
        kb.add(Text(BTN_RAID_CANCEL_READY, payload={"type": "raid_cancel_ready"}), color=KeyboardButtonColor.SECONDARY)
    else:
        kb.add(Text("Готов", payload={"type": "raid_pick", "raid": "puppet_theatre"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def raid_combat_keyboard(base_class: str, cooldowns: dict[str, int], subclass_id: str | None = None) -> str:
    """Патч 54: подписи берутся из общего реестра combat_modes.RAID — до этого
    были ДОСЛОВНЫМИ копиями группового PvE, и групповой обработчик (он раньше
    в LABELERS) перехватывал все три кнопки: рейд был непроходим, работали
    только навыки с уникальным payload.

    Кнопка побега здесь отсутствует НАМЕРЕННО (combat_modes.RAID.escape is
    None) — выйти из рейда нельзя, единственный выход — смерть всей группы
    (патч 53)."""
    kb = Keyboard(one_time=False)
    items: list[tuple[str, KeyboardButtonColor, dict | None]] = [
        # Патч 54: у атаки теперь есть и payload — диспетчеризация по нему не
        # зависит от подписи вовсе (второй рубеж, см. combat_modes).
        (_RAID.attack, KeyboardButtonColor.POSITIVE, {"type": "raid_attack"})
    ]
    for skill in skills_for_character(base_class, subclass_id):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        items.append((label, color, {"type": _RAID.skill_payload, "id": skill.id}))
    items.append((_RAID.target, KeyboardButtonColor.SECONDARY, {"type": "raid_open_target"}))
    items.append((_RAID.item, KeyboardButtonColor.SECONDARY, {"type": "raid_open_items"}))
    add_paired(kb, items)
    return kb.get_json()


def raid_target_keyboard(target_ids: list[int]) -> str:
    kb = Keyboard(inline=True)
    for i, cid in enumerate(target_ids, start=1):
        kb.add(Text(str(i), payload={"type": "raid_target_pick", "target": cid}), color=KeyboardButtonColor.SECONDARY)
        if i % _TARGET_ROW_WIDTH == 0:
            kb.row()
    if len(target_ids) % _TARGET_ROW_WIDTH != 0:
        kb.row()
    kb.add(Text("← Назад", payload={"type": "raid_target_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def raid_items_keyboard(stock: list) -> str:
    kb = Keyboard(inline=True)
    for idx, (elixir, count) in enumerate(stock):
        label = f"{elixir.emoji} {elixir.name} ×{count}"
        kb.add(Text(label, payload={"type": "raid_use_item", "id": elixir.id}), color=KeyboardButtonColor.SECONDARY)
        if idx % 2 == 1:
            kb.row()
    return kb.get_json()


def raid_waiting_keyboard() -> str:
    return Keyboard(one_time=False).get_json()
