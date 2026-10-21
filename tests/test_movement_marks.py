"""Подписи стрелок (2026-10-21): за воротами - координаты клетки, в поле -
значок того, что на соседней клетке (разлом, Монолит, рудник, озеро)."""

import json

from bot.keyboards import world as kb
from game.economy import fishing, mining
from services import rift_service


def _buttons(raw: str) -> list[dict]:
    return [b["action"] for row in json.loads(raw)["buttons"] for b in row]


def test_gate_buttons_show_target_coordinates() -> None:
    labels = [b["label"] for b in _buttons(kb.gate_direction_keyboard(0, 30))]
    assert "⬇️ (0; 29)" in labels and "⬅️ (-1; 30)" in labels


def test_arrow_marks_mine_lake_monolith() -> None:
    mine = mining.all_mines()[0]
    lake = fishing.all_lakes()[0]
    assert f"{kb.BTN_UP} (⛏)" in [b["label"] for b in _buttons(kb.movement_keyboard(mine.x, mine.y - 1))]
    assert f"{kb.BTN_RIGHT} (🎣)" in [b["label"] for b in _buttons(kb.movement_keyboard(lake.x - 1, lake.y))]
    assert f"{kb.BTN_DOWN} (🗿)" in [b["label"] for b in _buttons(kb.movement_keyboard(0, 1))]


def test_arrow_marks_rift_from_cache(monkeypatch) -> None:
    monkeypatch.setattr(rift_service, "_cells", frozenset({(10, 11)}))
    labels = [b["label"] for b in _buttons(kb.movement_keyboard(10, 10))]
    assert f"{kb.BTN_UP} (🌀)" in labels


def test_move_buttons_carry_direction_payload() -> None:
    by_label = {b["label"]: b for b in _buttons(kb.movement_keyboard(0, 1))}
    payload = by_label[f"{kb.BTN_DOWN} (🗿)"]["payload"]
    payload = json.loads(payload) if isinstance(payload, str) else payload
    assert payload == {"type": kb.MOVE_PAYLOAD_TYPE, "dx": 0, "dy": -1}


def test_bare_arrow_still_resolves_next_to_marked_cell() -> None:
    """Старая клавиатура без значка или стрелка, набранная рукой."""
    assert kb.resolve_direction(0, 1, kb.BTN_DOWN) == (0, -1)
    assert kb.resolve_direction(0, 1, f"{kb.BTN_DOWN} (🗿)") == (0, -1)
