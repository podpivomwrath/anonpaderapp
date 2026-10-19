"""2026-10-19: быстрые цели маунта кнопками - квест и след события."""

import json

from bot.handlers import mounts


def test_route_keyboard_has_quick_targets_and_toggle():
    kb = json.loads(mounts._route_keyboard(False, [("📜 К квесту", 1, -5), ("🐾 К следу", 3, 4)]))
    rows = [[b["action"] for b in row] for row in kb["buttons"]]
    assert rows[0][0]["label"] == "📜 К квесту (1; -5)"
    payload = rows[0][0]["payload"]
    assert (json.loads(payload) if isinstance(payload, str) else payload) == {"type": "mount_go", "x": 1, "y": -5}
    assert rows[1][0]["label"] == "🐾 К следу (3; 4)"
    assert "безопасным" in rows[-1][0]["label"]
    assert len(json.loads(mounts._route_keyboard(True))["buttons"]) == 1
