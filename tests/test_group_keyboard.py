"""Клавиатуры групп (патч 51, ч.2): payload-структура кнопок приглашения и
подтверждения выхода."""

import json

from bot.keyboards.group import group_invite_keyboard, leave_confirm_keyboard


def _payloads(keyboard_json: str) -> list[dict]:
    data = json.loads(keyboard_json)
    payloads = []
    for row in data["buttons"]:
        for btn in row:
            payload = btn["action"]["payload"]
            payloads.append(json.loads(payload) if isinstance(payload, str) else payload)
    return payloads


def test_group_invite_keyboard_has_accept_and_decline() -> None:
    payloads = _payloads(group_invite_keyboard(42))
    types = {p["type"] for p in payloads}
    assert types == {"group_invite_accept", "group_invite_decline"}
    assert all(p["invite_id"] == 42 for p in payloads)


def test_leave_confirm_keyboard_has_confirm_and_cancel() -> None:
    payloads = _payloads(leave_confirm_keyboard())
    types = {p["type"] for p in payloads}
    assert types == {"group_leave_confirm", "group_leave_cancel"}
