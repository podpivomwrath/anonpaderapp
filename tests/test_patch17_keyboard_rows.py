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
from bot.keyboards.elixir_shop import shop_keyboard
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
