"""Регресс: клавиатуры с полным набором эликсиров не должны превышать лимиты
VK (ошибка 911 "Keyboard format is invalid") — обнаружено при живой проверке
лавки зелий (патч 16/17).

combat_items_keyboard — INLINE (модальный выбор предмета в бою, патч 37 не
трогает): жёстче лимит — максимум 6 рядов И максимум 10 кнопок суммарно.

shop_keyboard — ОБЫЧНАЯ reply-клавиатура (патч 37: лавка — отдельный экран,
не inline поверх города) — лимит мягче: 10 рядов × 40 кнопок суммарно."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.combat_items import combat_items_keyboard
from bot.keyboards.elixir_shop import elixir_quantity_keyboard, shop_keyboard
from game.economy import elixir_config as ec
from config import Settings
from game.content_loader import load_elixirs

VK_INLINE_MAX_ROWS = 6
VK_INLINE_MAX_BUTTONS = 10
VK_REPLY_MAX_ROWS = 10
VK_REPLY_MAX_BUTTONS = 40


@pytest.fixture(autouse=True)
def _no_miniapp_button(monkeypatch):
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))


def _rows(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


def _assert_within_inline_limits(kb_json: str) -> None:
    rows = _rows(kb_json)
    assert len(rows) <= VK_INLINE_MAX_ROWS
    total_buttons = sum(len(row) for row in rows)
    assert total_buttons <= VK_INLINE_MAX_BUTTONS


def _assert_within_reply_limits(kb_json: str) -> None:
    rows = _rows(kb_json)
    assert len(rows) <= VK_REPLY_MAX_ROWS
    total_buttons = sum(len(row) for row in rows)
    assert total_buttons <= VK_REPLY_MAX_BUTTONS


def test_shop_keyboard_full_catalog_stays_within_reply_limits_and_is_not_inline() -> None:
    elixirs = list(load_elixirs().values())
    assert len(elixirs) == 10  # весь каталог патча 16 — уже под завязку
    kb_json = shop_keyboard(elixirs)
    assert json.loads(kb_json)["inline"] is False
    _assert_within_reply_limits(kb_json)


def test_combat_items_keyboard_full_stock_stays_within_inline_limits() -> None:
    stock = [(d, 1) for d in load_elixirs().values()]
    _assert_within_inline_limits(combat_items_keyboard(stock))


# --- Патч 39, ч.4: экран выбора количества при покупке зелья ---


def test_quantity_keyboard_hides_unaffordable_amounts() -> None:
    elixir = load_elixirs()["heal_small"]
    price = ec.ELIXIR_PRICES["heal_small"]
    # хватает ровно на ×1 и ×5, но не на ×10/×25
    kb_json = elixir_quantity_keyboard(elixir, farm_currency=price * 5)
    labels = {btn["action"]["label"] for row in _rows(kb_json) for btn in row}
    assert any(label.startswith("×1 ") for label in labels)
    assert any(label.startswith("×5 ") for label in labels)
    assert not any(label.startswith("×10 ") for label in labels)
    assert not any(label.startswith("×25 ") for label in labels)


def test_quantity_keyboard_shows_all_amounts_when_rich() -> None:
    elixir = load_elixirs()["heal_small"]
    price = ec.ELIXIR_PRICES["heal_small"]
    kb_json = elixir_quantity_keyboard(elixir, farm_currency=price * 25)
    labels = {btn["action"]["label"] for row in _rows(kb_json) for btn in row}
    for qty in ec.SHOP_BULK_QUANTITIES:
        assert any(label.startswith(f"×{qty} ") for label in labels)


def test_quantity_keyboard_back_button_present_even_when_poor() -> None:
    elixir = load_elixirs()["heal_small"]
    kb_json = elixir_quantity_keyboard(elixir, farm_currency=0)
    labels = {btn["action"]["label"] for row in _rows(kb_json) for btn in row}
    assert "← Назад" in labels
