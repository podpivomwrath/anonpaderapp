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


async def test_home_target_follows_current_city(db_session, make_character):
    """2026-10-31: «Домой» - в родной город; кнопка несёт флаг, а не только
    координаты, чтобы после смены города ехать в новый. Дома - не предлагается."""
    from game.world import world_config as wc

    c = await make_character(level=10)
    c.region = "docks"
    c.pos_x, c.pos_y = 5, 5
    targets = await mounts._quick_targets(db_session, c)
    assert (mounts.HOME_LABEL, *wc.CITY_COORDS["docks"]) in targets
    kb = json.loads(mounts._route_keyboard(False, [(mounts.HOME_LABEL, 30, 0)]))
    payload = kb["buttons"][0][0]["action"]["payload"]
    assert (json.loads(payload) if isinstance(payload, str) else payload)["home"] is True
    c.pos_x, c.pos_y = wc.CITY_COORDS["docks"]
    assert all(t[0] != mounts.HOME_LABEL for t in await mounts._quick_targets(db_session, c))
