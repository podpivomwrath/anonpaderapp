"""Патч 17: границы карты, кнопка входа в город вместо стрелки, выбор
направления при выходе из города."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.world import (
    BTN_DOWN,
    BTN_LEFT,
    BTN_RIGHT,
    BTN_UP,
    gate_direction_keyboard,
    movement_keyboard,
    resolve_direction,
)
from bot.onboarding_texts import REGION_TITLES
from config import Settings
from game.world import grid
from game.world import world_config as wc


@pytest.fixture(autouse=True)
def _no_miniapp_button(monkeypatch):
    """Изолируем от реального .env — см. tests/test_appraiser_keyboard.py."""
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))


def _labels(kb_json: str) -> list[str]:
    kb = json.loads(kb_json)
    return [btn["action"]["label"] for row in kb["buttons"] for btn in row]


def test_movement_keyboard_keeps_direction_leading_out_of_bounds() -> None:
    """Патч 31, п.7: кнопка направления за границу больше не скрывается —
    раскладка не должна «прыгать» (см. докстринг movement_keyboard)."""
    labels = _labels(movement_keyboard(wc.BOUNDS_MAX, 0))
    assert BTN_RIGHT in labels
    assert BTN_UP in labels and BTN_DOWN in labels and BTN_LEFT in labels


def test_movement_keyboard_shows_city_name_instead_of_arrow() -> None:
    # (49;50) — соседняя клетка вправо (50;50) это Обетованный Кряж
    labels = _labels(movement_keyboard(49, 50))
    assert REGION_TITLES["ridge"] in labels
    assert BTN_RIGHT not in labels
    assert BTN_UP in labels  # (49;51) — за границей (BOUNDS_MAX=50), но кнопка на месте
    assert BTN_DOWN in labels and BTN_LEFT in labels


def test_resolve_direction_matches_city_label() -> None:
    assert resolve_direction(49, 50, REGION_TITLES["ridge"]) == (1, 0)


def test_resolve_direction_resolves_out_of_bounds_arrow() -> None:
    """Патч 31, п.7: resolve_direction больше не блокирует по границе —
    легальность хода теперь проверяет bot/handlers/world.py::move через
    grid.in_bounds после резолва направления."""
    assert resolve_direction(wc.BOUNDS_MAX, 0, BTN_RIGHT) == (1, 0)


def test_resolve_direction_none_for_stale_city_label_far_from_city() -> None:
    assert resolve_direction(0, 0, REGION_TITLES["ridge"]) is None


@pytest.mark.parametrize("region,coords", list(wc.CITY_COORDS.items()))
def test_gate_direction_keyboard_offers_exactly_two_inward_directions(region, coords) -> None:
    x, y = coords
    kb = json.loads(gate_direction_keyboard(x, y))
    buttons = [btn for row in kb["buttons"] for btn in row]
    assert len(buttons) == 2
    for btn in buttons:
        dx, dy = btn["action"]["payload"]["dx"], btn["action"]["payload"]["dy"]
        assert grid.in_bounds(x + dx, y + dy)
