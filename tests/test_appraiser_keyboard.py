"""Клавиатура скупщика (патч 9, блок 3): продать всё / поштучно."""

import json

from bot.keyboards.appraiser import SELL_ALL_ID, appraiser_keyboard
from game.content_loader import TrophyDef


def _defs():
    ash = TrophyDef(id="ash_dust", emoji="⚪", name="Пепельная крошка", sell_price=2)
    blood = TrophyDef(id="blood_shard", emoji="🟣", name="Кровяной осколок", sell_price=80)
    return ash, blood


def test_empty_stock_has_no_buttons() -> None:
    kb = json.loads(appraiser_keyboard([]))
    assert kb["buttons"] == []


def test_sell_all_button_totals_all_grades() -> None:
    ash, blood = _defs()
    kb = json.loads(appraiser_keyboard([(ash, 3), (blood, 1)]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    sell_all = next(b for b in buttons if b["action"]["payload"]["id"] == SELL_ALL_ID)
    assert "86 зол." in sell_all["action"]["label"]  # 3*2 + 1*80


def test_one_button_per_grade_in_stock() -> None:
    ash, blood = _defs()
    kb = json.loads(appraiser_keyboard([(ash, 3), (blood, 1)]))
    buttons = [btn for row in kb["buttons"] for btn in row]
    payload_ids = {b["action"]["payload"]["id"] for b in buttons}
    assert payload_ids == {SELL_ALL_ID, "ash_dust", "blood_shard"}
    ash_button = next(b for b in buttons if b["action"]["payload"]["id"] == "ash_dust")
    assert "⚪" in ash_button["action"]["label"] and "×3" in ash_button["action"]["label"]
