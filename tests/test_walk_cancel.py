"""Отмена пешего перехода (2026-10-19): одна кнопка в пути, отмена оставляет
на клетке, откуда вышел."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from bot.keyboards import world as wkb
from services import movement_service


def test_walking_keyboard_has_cancel() -> None:
    rows = json.loads(wkb.walking_keyboard())["buttons"]
    payloads = [b["action"].get("payload") for row in rows for b in row]
    payloads = [json.loads(p) if isinstance(p, str) else p for p in payloads if p]
    assert wkb.WALK_CANCEL_PAYLOAD in payloads


def test_cancel_keeps_the_start_cell() -> None:
    c = SimpleNamespace(pos_x=4, pos_y=-7, travel_target_x=None, travel_target_y=None, travel_arrives_at=None)
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    movement_service.start_travel(c, 1, 0, now)
    assert movement_service.is_traveling(c, now)
    movement_service.cancel_travel(c)
    assert (c.pos_x, c.pos_y) == (4, -7) and not movement_service.is_traveling(c, now)
    assert not movement_service.resolve_arrival(c, now)
