"""Регресс: клавиатуры с полным набором эликсиров не должны превышать лимиты
VK для INLINE-клавиатур (ошибка 911 "Keyboard format is invalid") —
обнаружено при живой проверке лавки зелий (патч 16/17).

Инлайн-клавиатуры VK ограничены жёстче обычных reply-клавиатур: максимум
6 рядов И максимум 10 кнопок суммарно (а не 10 рядов × 40 кнопок, как у
reply-клавиатуры) — поэтому полный каталог из 10 эликсиров уже занимает
весь лимит и не оставляет места для кнопки мини-аппа."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.combat_items import combat_items_keyboard
from bot.keyboards.elixir_shop import shop_keyboard
from config import Settings
from game.content_loader import load_elixirs

VK_INLINE_MAX_ROWS = 6
VK_INLINE_MAX_BUTTONS = 10


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


def test_shop_keyboard_full_catalog_stays_within_inline_limits() -> None:
    elixirs = list(load_elixirs().values())
    assert len(elixirs) == 10  # весь каталог патча 16 — уже под завязку
    _assert_within_inline_limits(shop_keyboard(elixirs))


def test_combat_items_keyboard_full_stock_stays_within_inline_limits() -> None:
    stock = [(d, 1) for d in load_elixirs().values()]
    _assert_within_inline_limits(combat_items_keyboard(stock))
