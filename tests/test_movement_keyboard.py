"""Клавиатура карты (патч 25, п.1/п.4/п.7): крест перемещения + условные
кнопки Горстка пепла/Маунт."""

import json

from bot import ash_handful_state
from bot.keyboards.world import BTN_ASH_HANDFUL, BTN_EXPLORE, BTN_MOUNT, movement_keyboard


def _labels(kb_json: str) -> list[str]:
    rows = json.loads(kb_json)["buttons"]
    return [btn["action"]["label"] for row in rows for btn in row]


def test_explore_always_present() -> None:
    labels = _labels(movement_keyboard(0, 0))
    assert BTN_EXPLORE in labels


def test_ash_button_hidden_by_default() -> None:
    peer_id = 424242
    ash_handful_state.clear(peer_id)
    labels = _labels(movement_keyboard(0, 0, peer_id))
    assert BTN_ASH_HANDFUL not in labels


def test_ash_button_shown_when_pending() -> None:
    peer_id = 424243
    ash_handful_state.mark(peer_id)
    try:
        labels = _labels(movement_keyboard(0, 0, peer_id))
        assert BTN_ASH_HANDFUL in labels
    finally:
        ash_handful_state.clear(peer_id)


def test_mount_button_only_when_has_mount() -> None:
    assert BTN_MOUNT not in _labels(movement_keyboard(0, 0))
    assert BTN_MOUNT in _labels(movement_keyboard(0, 0, has_mount=True))
