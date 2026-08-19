"""Клавиатуры группового PvE-боя и очереди исследования (патч 51, ч.3/4)."""

import json

from bot.keyboards.group_combat import (
    BTN_GROUP_ATTACK,
    BTN_GROUP_ITEM,
    BTN_GROUP_TARGET,
    group_combat_keyboard,
    group_target_keyboard,
)
from bot.keyboards.group_explore import group_ready_keyboard
from bot.keyboards.pvp import BTN_PVP_ATTACK
from bot.keyboards.world import BTN_ATTACK


def _all_texts(keyboard_json: str) -> list[str]:
    data = json.loads(keyboard_json)
    return [btn["action"]["label"] for row in data["buttons"] for btn in row]


def test_group_attack_button_text_distinct_from_solo_and_pvp() -> None:
    assert BTN_GROUP_ATTACK != BTN_ATTACK
    assert BTN_GROUP_ATTACK != BTN_PVP_ATTACK


def test_group_combat_keyboard_has_attack_target_and_item() -> None:
    kb = group_combat_keyboard("warrior", {})
    texts = _all_texts(kb)
    assert BTN_GROUP_ATTACK in texts
    assert BTN_GROUP_TARGET in texts
    assert BTN_GROUP_ITEM in texts


def test_group_target_keyboard_numbers_mobs() -> None:
    kb = group_target_keyboard([101, 102, 103])
    texts = _all_texts(kb)
    assert texts[:3] == ["1", "2", "3"]
    assert "← Назад" in texts


def test_group_ready_keyboard_has_cancel_button() -> None:
    texts = _all_texts(group_ready_keyboard())
    assert "Отменить" in texts
