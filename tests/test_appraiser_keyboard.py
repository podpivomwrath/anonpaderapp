"""Клавиатура скупщика (патч 9, блок 3): продать всё / поштучно."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.appraiser import BTN_SELL_GEAR, SELL_ALL_ID, appraiser_keyboard
from config import Settings
from game.content_loader import TrophyDef


def _defs():
    ash = TrophyDef(id="ash_dust", emoji="⚪", name="Пепельная крошка", sell_price=2)
    blood = TrophyDef(id="blood_shard", emoji="🟣", name="Кровяной осколок", sell_price=80)
    return ash, blood


@pytest.fixture(autouse=True)
def _no_miniapp_button(monkeypatch):
    """Изолируем тесты от реального .env — иначе кнопка мини-аппа (ux-patch-10)
    примешивается из настоящего VK_MINIAPP_URL и ломает подсчёт кнопок."""
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))


def test_empty_stock_has_only_sell_gear_button() -> None:
    """Пустой стек трофеев — остаётся только [Продать снаряжение] (патч 11),
    без единой кнопки продажи трофеев."""
    kb = json.loads(appraiser_keyboard([]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    assert len(buttons) == 1
    assert buttons[0]["action"]["label"] == BTN_SELL_GEAR
    assert "payload" not in buttons[0]["action"]


def test_sell_all_button_totals_all_grades() -> None:
    ash, blood = _defs()
    kb = json.loads(appraiser_keyboard([(ash, 3), (blood, 1)]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    sell_all = next(b for b in buttons if b["action"].get("payload", {}).get("id") == SELL_ALL_ID)
    assert "86 зол." in sell_all["action"]["label"]  # 3*2 + 1*80


def test_one_button_per_grade_in_stock() -> None:
    ash, blood = _defs()
    kb = json.loads(appraiser_keyboard([(ash, 3), (blood, 1)]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    payload_ids = {b["action"]["payload"]["id"] for b in buttons if "payload" in b["action"]}
    assert payload_ids == {SELL_ALL_ID, "ash_dust", "blood_shard"}
    ash_button = next(b for b in buttons if b["action"].get("payload", {}).get("id") == "ash_dust")
    assert "⚪" in ash_button["action"]["label"] and "×3" in ash_button["action"]["label"]


def test_sell_gear_button_always_present_with_stock() -> None:
    ash, _ = _defs()
    kb = json.loads(appraiser_keyboard([(ash, 1)]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    assert any(b["action"]["label"] == BTN_SELL_GEAR for b in buttons)
