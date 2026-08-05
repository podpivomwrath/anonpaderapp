"""Клавиатура города (патч 26): чужой город — доступен только Скупщик среди
NPC; личные меню (Инвентарь/Характеристики/Задания/Пресеты/Маунт/Ворота/
Отдых) работают как обычно."""

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
    BTN_MENTOR,
    BTN_MOUNT,
    BTN_PRESETS,
    BTN_REST,
    BTN_STATS,
    city_menu_keyboard,
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


def test_own_city_shows_all_npc_buttons() -> None:
    labels = _labels(city_menu_keyboard(FakeCharacter(), has_mount=True, is_foreign=False))
    assert {BTN_MENTOR, BTN_MARKET, BTN_ELIXIR_SHOP, BTN_KEEPER, BTN_APPRAISER}.issubset(labels)


def test_foreign_city_hides_mentor_market_elixir_keeper() -> None:
    labels = _labels(city_menu_keyboard(FakeCharacter(), has_mount=True, is_foreign=True))
    assert BTN_MENTOR not in labels
    assert BTN_MARKET not in labels
    assert BTN_ELIXIR_SHOP not in labels
    assert BTN_KEEPER not in labels


def test_foreign_city_keeps_appraiser_and_personal_menus() -> None:
    labels = _labels(city_menu_keyboard(FakeCharacter(), has_mount=True, is_foreign=True))
    assert BTN_APPRAISER in labels
    assert BTN_GATE in labels
    assert BTN_REST in labels
    assert BTN_INVENTORY in labels
    assert BTN_STATS in labels
    assert BTN_DAILIES in labels
    assert BTN_PRESETS in labels  # персонаж с подклассом
    assert BTN_MOUNT in labels  # has_mount=True


def test_foreign_city_hides_keeper_even_at_unlock_level() -> None:
    high_level = FakeCharacter(level=bc.SUBCLASS_UNLOCK_MIN_LEVEL, subclass=None)
    assert BTN_KEEPER not in _labels(city_menu_keyboard(high_level, is_foreign=True))
    assert BTN_KEEPER in _labels(city_menu_keyboard(high_level, is_foreign=False))
