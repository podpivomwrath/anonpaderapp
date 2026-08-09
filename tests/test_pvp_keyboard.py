"""Клавиатуры открытого PvP (патч 22/30/38): дуэльная/массовая боевая
клавиатура + предметы (патч 30, баг 3, п.3) + выбор цели (патч 38)."""

import json

from bot.keyboards.pvp import (
    BTN_PVP_ATTACK,
    BTN_PVP_ITEM,
    BTN_PVP_TARGET,
    pvp_combat_keyboard,
    pvp_items_keyboard,
    pvp_target_keyboard,
)
from game.content_loader import ElixirDef


def _labels(kb_json: str) -> set[str]:
    kb = json.loads(kb_json)
    return {btn["action"]["label"] for row in kb["buttons"] for btn in row}


def test_combat_keyboard_has_attack_skills_and_item_button() -> None:
    labels = _labels(pvp_combat_keyboard("warrior", {}))
    assert BTN_PVP_ATTACK in labels
    assert BTN_PVP_ITEM in labels


def test_combat_keyboard_item_text_differs_from_pve() -> None:
    """Патч 30: если бы текст совпадал с PvE, vkbottle навсегда перехватывал
    бы нажатие в combat.py (зарегистрирован раньше pvp.py) — см. докстринг
    bot/keyboards/pvp.py."""
    from bot.keyboards.world import BTN_ITEM

    assert BTN_PVP_ITEM != BTN_ITEM


def _elixir(id_: str, category: str = "heal") -> ElixirDef:
    return ElixirDef(id=id_, name=id_, emoji="🧪", category=category)


def test_items_keyboard_uses_pvp_specific_payload() -> None:
    kb = json.loads(pvp_items_keyboard([(_elixir("heal_small"), 2)]))
    button = kb["buttons"][0][0]
    assert button["action"]["payload"]["type"] == "pvp_use_item"
    assert button["action"]["payload"]["id"] == "heal_small"


def test_items_keyboard_two_per_row() -> None:
    stock = [(_elixir(f"e{i}"), 1) for i in range(3)]
    kb = json.loads(pvp_items_keyboard(stock))
    assert len(kb["buttons"]) == 2  # 2 в первом ряду + 1 во втором
    assert len(kb["buttons"][0]) == 2
    assert len(kb["buttons"][1]) == 1


# --- Патч 38: кнопка [🎯 Цель] — только в массовом бою ---


def test_combat_keyboard_hides_target_button_by_default() -> None:
    """По умолчанию (дуэль 1×1) — противник ровно один, выбор не нужен."""
    assert BTN_PVP_TARGET not in _labels(pvp_combat_keyboard("warrior", {}))


def test_combat_keyboard_shows_target_button_for_mass() -> None:
    assert BTN_PVP_TARGET in _labels(pvp_combat_keyboard("warrior", {}, show_target=True))


def test_pvp_target_keyboard_numbers_enemies_and_back_last() -> None:
    kb = json.loads(pvp_target_keyboard([11, 22, 33]))
    rows = kb["buttons"]
    numbered = rows[0]
    assert [b["action"]["label"] for b in numbered] == ["1", "2", "3"]
    assert [b["action"]["payload"]["target"] for b in numbered] == [11, 22, 33]
    assert all(b["action"]["payload"]["type"] == "pvp_target_pick" for b in numbered)
    back = rows[-1][-1]
    assert back["action"]["label"] == "← Назад"
    assert back["action"]["payload"] == {"type": "pvp_target_back"}
