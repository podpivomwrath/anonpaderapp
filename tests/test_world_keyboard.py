"""Клавиатуры города (патч 39): кварталы — Главная площадь / Таверна /
Торговый квартал, вместо монолитной city_menu_keyboard (патч 26 остаётся в
силе — в чужом городе доступен только Торговый квартал со скупщиком)."""

import json
from dataclasses import dataclass

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.world import (
    BTN_APPRAISER,
    BTN_DAILIES,
    BTN_ELIXIR_SHOP,
    BTN_GATE,
    BTN_INVENTORY,
    BTN_KEEPER,
    BTN_MARKET,
    BTN_MARKET_QUARTER,
    BTN_MENTOR,
    BTN_MOUNT,
    BTN_PRESETS,
    BTN_REST,
    BTN_SQUARE_BACK,
    BTN_STATS,
    BTN_TAVERN,
    city_square_keyboard,
    market_quarter_keyboard,
    tavern_keyboard,
)
from config import Settings
from game.combat import balance_config as bc


@dataclass
class FakeCharacter:
    level: int = 40
    subclass: str | None = "guardian"


@pytest.fixture(autouse=True)
def _no_miniapp_button(monkeypatch):
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))


def _labels(kb_json: str) -> set[str]:
    kb = json.loads(kb_json)
    return {btn["action"]["label"] for row in kb["buttons"] for btn in row}


def _rows(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


# --- Главная площадь ---


def test_square_own_city_shows_mentor_and_both_quarters() -> None:
    labels = _labels(city_square_keyboard(FakeCharacter(), has_mount=True, is_foreign=False))
    assert {BTN_MENTOR, BTN_GATE, BTN_TAVERN, BTN_MARKET_QUARTER, BTN_MOUNT}.issubset(labels)


def test_square_foreign_city_hides_mentor_and_tavern() -> None:
    labels = _labels(city_square_keyboard(FakeCharacter(), has_mount=True, is_foreign=True))
    assert BTN_MENTOR not in labels
    assert BTN_TAVERN not in labels
    assert BTN_MARKET_QUARTER in labels
    assert BTN_GATE in labels
    assert BTN_MOUNT in labels  # транспорт — не NPC, доступен и чужаку


def test_square_no_mount_button_without_mount() -> None:
    assert BTN_MOUNT not in _labels(city_square_keyboard(FakeCharacter(), has_mount=False))


def test_square_rows_bounded() -> None:
    rows = _rows(city_square_keyboard(FakeCharacter(), has_mount=True, is_foreign=False))
    assert len(rows) <= 6


# --- Таверна ---


def test_tavern_shows_personal_menus_and_back_last() -> None:
    kb_json = tavern_keyboard(FakeCharacter())
    labels = _labels(kb_json)
    assert {BTN_REST, BTN_STATS, BTN_DAILIES, BTN_KEEPER, BTN_PRESETS, BTN_SQUARE_BACK}.issubset(labels)
    rows = _rows(kb_json)
    assert rows[-1][-1]["action"]["label"] == BTN_SQUARE_BACK


def test_tavern_hides_keeper_below_unlock_level() -> None:
    low_level = FakeCharacter(level=bc.SUBCLASS_UNLOCK_MIN_LEVEL - 1, subclass=None)
    assert BTN_KEEPER not in _labels(tavern_keyboard(low_level))


def test_tavern_shows_keeper_at_unlock_level() -> None:
    high_level = FakeCharacter(level=bc.SUBCLASS_UNLOCK_MIN_LEVEL, subclass=None)
    assert BTN_KEEPER in _labels(tavern_keyboard(high_level))


def test_tavern_hides_presets_without_subclass() -> None:
    no_subclass = FakeCharacter(subclass=None)
    assert BTN_PRESETS not in _labels(tavern_keyboard(no_subclass))


def test_tavern_rows_bounded() -> None:
    rows = _rows(tavern_keyboard(FakeCharacter()))
    assert len(rows) <= 6


def test_tavern_none_character_still_works() -> None:
    """Легаси-вызовы без character (напр. bot/handlers/respawn.py) не падают."""
    labels = _labels(tavern_keyboard(None))
    assert BTN_KEEPER not in labels
    assert BTN_PRESETS not in labels
    assert BTN_REST in labels


# --- Торговый квартал ---


def test_market_quarter_own_city_shows_all_and_back_last() -> None:
    kb_json = market_quarter_keyboard(is_foreign=False)
    labels = _labels(kb_json)
    assert {BTN_APPRAISER, BTN_ELIXIR_SHOP, BTN_INVENTORY, BTN_MARKET, BTN_SQUARE_BACK}.issubset(labels)
    rows = _rows(kb_json)
    assert rows[-1][-1]["action"]["label"] == BTN_SQUARE_BACK


def test_market_quarter_foreign_hides_elixir_and_market_keeps_appraiser_inventory() -> None:
    labels = _labels(market_quarter_keyboard(is_foreign=True))
    assert BTN_ELIXIR_SHOP not in labels
    assert BTN_MARKET not in labels
    assert BTN_APPRAISER in labels
    assert BTN_INVENTORY in labels
    assert BTN_SQUARE_BACK in labels


def test_market_quarter_rows_bounded() -> None:
    rows = _rows(market_quarter_keyboard(is_foreign=False))
    assert len(rows) <= 6
