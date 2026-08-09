"""Клавиатура скупщика (патч 9, блок 3): продать всё / поштучно.
Патч 35: группировка снаряжения по редкости + подробный режим с пагинацией."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.appraiser import (
    BTN_SELL_GEAR,
    GEAR_DETAIL_PAGE_SIZE,
    SELL_ALL_ID,
    appraiser_keyboard,
    sell_confirm_keyboard,
    sell_gear_detail_keyboard,
    sell_gear_main_keyboard,
)
from config import Settings
from game.content_loader import ItemRarityDef, ItemRaritySuffix, TrophyDef
from models import Item


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


# --- Патч 35: основной экран продажи снаряжения, сгруппированный по редкости ---


def _rdef(rid: str, emoji: str) -> ItemRarityDef:
    return ItemRarityDef(id=rid, emoji=emoji, name=rid, mult=1.0, suffix=ItemRaritySuffix())


def _kb_rows(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


def test_sell_gear_main_keyboard_one_button_per_present_rarity(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    common = _rdef("common", "⚪")
    rare = _rdef("rare", "🟣")
    items_common = [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(12)]
    items_rare = [Item(id=100, name="Y", slot="helmet", base_stats={})]
    groups = [(common, items_common, 216), (rare, items_rare, 80)]

    kb = json.loads(sell_gear_main_keyboard(groups, 296))
    buttons = [btn for row in kb["buttons"] for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"sell_all_gear", "sell_rarity", "gear_detail", "gear_back"}
    rarity_labels = {
        b["action"]["label"] for b in buttons if b["action"].get("payload", {}).get("type") == "sell_rarity"
    }
    assert rarity_labels == {"Продать ⚪ ×12 — 216 зол.", "Продать 🟣 ×1 — 80 зол."}


def test_sell_gear_main_keyboard_rows_bounded_even_with_many_items(monkeypatch) -> None:
    """Патч 35: сколько бы предметов ни было в редкости, экран не превышает
    лимит клавиатуры VK (10 строк) — группировка вместо кнопки на предмет."""
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    all_rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    groups = [
        (_rdef(rid, "⚪"), [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(20)], 100)
        for rid in all_rarities
    ]
    rows = _kb_rows(sell_gear_main_keyboard(groups, 500))
    assert len(rows) <= 10


def test_sell_gear_main_keyboard_empty_groups_has_only_back(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    kb = json.loads(sell_gear_main_keyboard([], 0))
    buttons = [btn for row in kb["buttons"] for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"gear_back"}


# --- Патч 35: подробный режим с пагинацией ---


def test_sell_gear_detail_keyboard_numbers_items_on_page(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    items = [Item(id=i, name=f"X{i}", slot="weapon", base_stats={}) for i in range(1, 4)]
    kb = json.loads(sell_gear_detail_keyboard(items, page=1, total_pages=2))
    buttons = [btn for row in kb["buttons"] for btn in row]
    numbered = [b for b in buttons if b["action"].get("payload", {}).get("type") == "sell_item"]
    assert [b["action"]["label"] for b in numbered] == ["1", "2", "3"]
    assert [b["action"]["payload"]["item"] for b in numbered] == [1, 2, 3]
    assert all(b["action"]["payload"]["page"] == 1 for b in numbered)


def test_sell_gear_detail_keyboard_pagination_buttons_respect_edges(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    items = [Item(id=1, name="X", slot="weapon", base_stats={})]

    first_page = json.loads(sell_gear_detail_keyboard(items, page=1, total_pages=3))
    labels = {b["action"]["label"] for row in first_page["buttons"] for b in row}
    assert "Стр. →" in labels
    assert "← Стр." not in labels

    last_page = json.loads(sell_gear_detail_keyboard(items, page=3, total_pages=3))
    labels = {b["action"]["label"] for row in last_page["buttons"] for b in row}
    assert "← Стр." in labels
    assert "Стр. →" not in labels


def test_sell_gear_detail_keyboard_rows_bounded_at_page_size(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    items = [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(GEAR_DETAIL_PAGE_SIZE)]
    rows = _kb_rows(sell_gear_detail_keyboard(items, page=1, total_pages=1))
    assert len(rows) <= 10


# --- Патч 35: предупреждение о продаже снаряжения лучше надетого ---


def test_sell_confirm_keyboard_carries_confirm_payload_and_cancel() -> None:
    kb = json.loads(sell_confirm_keyboard({"type": "sell_rarity_confirm", "rarity": "rare"}))
    buttons = [btn for row in kb["buttons"] for btn in row]
    confirm = next(b for b in buttons if b["action"]["label"] == "Да, продать")
    assert confirm["action"]["payload"] == {"type": "sell_rarity_confirm", "rarity": "rare"}
    cancel = next(b for b in buttons if b["action"]["label"] == "Отмена")
    assert cancel["action"]["payload"] == {"type": "gear_back_main"}
