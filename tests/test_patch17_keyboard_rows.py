"""Регресс: клавиатуры с полным набором эликсиров не должны превышать лимит
VK на число рядов (ошибка 911 "Keyboard format is invalid: buttons contain
too much rows") — обнаружено при живой проверке лавки зелий (патч 16/17)."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.combat_items import combat_items_keyboard
from bot.keyboards.elixir_shop import shop_keyboard
from config import Settings
from game.content_loader import load_elixirs

VK_MAX_KEYBOARD_ROWS = 10


@pytest.fixture(autouse=True)
def _no_miniapp_button(monkeypatch):
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))


def _row_count(kb_json: str) -> int:
    return len(json.loads(kb_json)["buttons"])


def test_shop_keyboard_full_catalog_stays_within_row_limit() -> None:
    elixirs = list(load_elixirs().values())
    assert len(elixirs) == 10  # весь каталог патча 16
    assert _row_count(shop_keyboard(elixirs)) <= VK_MAX_KEYBOARD_ROWS


def test_combat_items_keyboard_full_stock_stays_within_row_limit() -> None:
    stock = [(d, 1) for d in load_elixirs().values()]
    assert _row_count(combat_items_keyboard(stock)) <= VK_MAX_KEYBOARD_ROWS
