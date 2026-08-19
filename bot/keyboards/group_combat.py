"""Клавиатуры группового PvE-боя (патч 51, ч.4).

ВАЖНО: текст/payload НАМЕРЕННО отличаются и от соло-PvE (bot/keyboards/world.py
— BTN_ATTACK="🗡️ Атака", payload {"type":"skill"}), и от PvP (bot/keyboards/
pvp.py — BTN_PVP_ATTACK="🗡️ Атаковать", payload {"type":"pvp_skill"}) — по той
же причине, что описана в bot/keyboards/pvp.py: vkbottle диспетчерит по
ПЕРВОМУ зарегистрированному совпадающему правилу, совпадающий текст/payload
у двух лейблеров означал бы, что один обработчик никогда не вызовется."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.layout import add_paired
from game.combat.base_skills import skills_for_character

_TARGET_ROW_WIDTH = 5

BTN_GROUP_ATTACK = "⚔️ Ударить"
BTN_GROUP_ITEM = "🎒 Снаряжение"
BTN_GROUP_TARGET = "🎯 Цель"


def group_combat_keyboard(
    base_class: str, cooldowns: dict[str, int], subclass_id: str | None = None,
) -> str:
    """Как pvp_combat_keyboard, но без побега (сбежать из группового боя
    нельзя, как и из массового PvP) и ВСЕГДА с выбором цели (мобов, как
    правило, несколько — по числу участников)."""
    kb = Keyboard(one_time=False)
    items: list[tuple[str, KeyboardButtonColor, dict | None]] = [
        (BTN_GROUP_ATTACK, KeyboardButtonColor.POSITIVE, None)
    ]
    for skill in skills_for_character(base_class, subclass_id):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        items.append((label, color, {"type": "group_pve_skill", "id": skill.id}))
    items.append((BTN_GROUP_TARGET, KeyboardButtonColor.SECONDARY, None))
    items.append((BTN_GROUP_ITEM, KeyboardButtonColor.SECONDARY, None))
    add_paired(kb, items)
    return kb.get_json()


def group_target_keyboard(mob_ids: list[int]) -> str:
    kb = Keyboard(inline=True)
    for i, cid in enumerate(mob_ids, start=1):
        kb.add(
            Text(str(i), payload={"type": "group_pve_target_pick", "target": cid}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if i % _TARGET_ROW_WIDTH == 0:
            kb.row()
    if len(mob_ids) % _TARGET_ROW_WIDTH != 0:
        kb.row()
    kb.add(Text("← Назад", payload={"type": "group_pve_target_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def group_items_keyboard(stock: list) -> str:
    """Список зелий/эликсиров в групповом PvE-бою — payload {"type":
    "group_pve_use_item"}, НАМЕРЕННО отличный и от соло-PvE ({"type":"use_item"}),
    и от PvP ({"type":"pvp_use_item"}) по той же причине, что и BTN_GROUP_ATTACK."""
    kb = Keyboard(inline=True)
    for idx, (elixir, count) in enumerate(stock):
        label = f"{elixir.emoji} {elixir.name} ×{count}"
        kb.add(
            Text(label, payload={"type": "group_pve_use_item", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if idx % 2 == 1:
            kb.row()
    return kb.get_json()


def group_waiting_keyboard() -> str:
    kb = Keyboard(one_time=False)
    return kb.get_json()
