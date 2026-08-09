"""Клавиатуры скупщика (патч 9, блок 3; патч 35 — группировка снаряжения по
редкости + подробный режим с пагинацией; патч 37 — дерево экранов: клавиатуры
ОБЫЧНЫЕ, не inline, заменяют городскую целиком, [← Назад] последней кнопкой)."""

import json

import pytest

import bot.keyboards.world as world_kb
from bot.keyboards.appraiser import (
    GEAR_DETAIL_PAGE_SIZE,
    SELL_ALL_ID,
    appraiser_root_keyboard,
    appraiser_trophies_keyboard,
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


def _kb_rows(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


def _last_button(kb_json: str) -> dict:
    rows = _kb_rows(kb_json)
    return rows[-1][-1]


# --- Патч 37: корневой экран скупщика (2 действия + назад) ---


def test_appraiser_root_keyboard_is_not_inline() -> None:
    kb = json.loads(appraiser_root_keyboard())
    assert kb["inline"] is False


def test_appraiser_root_keyboard_has_two_actions_and_back_last() -> None:
    kb_json = appraiser_root_keyboard()
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    payload_types = [b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]]
    assert payload_types == ["appraiser_trophies", "appraiser_gear", "appraiser_back"]
    assert _last_button(kb_json)["action"]["payload"]["type"] == "appraiser_back"


# --- Патч 9/37: подэкран трофеев ---


def test_appraiser_trophies_keyboard_is_not_inline_and_back_last() -> None:
    ash, blood = _defs()
    kb_json = appraiser_trophies_keyboard([(ash, 3), (blood, 1)])
    kb = json.loads(kb_json)
    assert kb["inline"] is False
    assert _last_button(kb_json)["action"]["payload"] == {"type": "appraiser_root"}


def test_appraiser_trophies_keyboard_empty_stock_still_has_back() -> None:
    kb_json = appraiser_trophies_keyboard([])
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"appraiser_root"}


def test_appraiser_trophies_keyboard_sell_all_totals_and_one_per_grade() -> None:
    ash, blood = _defs()
    kb_json = appraiser_trophies_keyboard([(ash, 3), (blood, 1)])
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    sell_all = next(b for b in buttons if b["action"].get("payload", {}).get("id") == SELL_ALL_ID)
    assert "86 зол." in sell_all["action"]["label"]  # 3*2 + 1*80
    payload_ids = {b["action"]["payload"].get("id") for b in buttons if b["action"].get("payload", {}).get("type") == "sell_trophies"}
    assert payload_ids == {SELL_ALL_ID, "ash_dust", "blood_shard"}


# --- Патч 35/37: основной экран продажи снаряжения, сгруппированный по редкости ---


def _rdef(rid: str, emoji: str) -> ItemRarityDef:
    return ItemRarityDef(id=rid, emoji=emoji, name=rid, mult=1.0, suffix=ItemRaritySuffix())


def test_sell_gear_main_keyboard_is_not_inline_and_back_last() -> None:
    common = _rdef("common", "⚪")
    items_common = [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(12)]
    kb_json = sell_gear_main_keyboard([(common, items_common, 216)], 216)
    kb = json.loads(kb_json)
    assert kb["inline"] is False
    assert _last_button(kb_json)["action"]["payload"] == {"type": "appraiser_root"}


def test_sell_gear_main_keyboard_one_button_per_present_rarity() -> None:
    common = _rdef("common", "⚪")
    rare = _rdef("rare", "🟣")
    items_common = [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(12)]
    items_rare = [Item(id=100, name="Y", slot="helmet", base_stats={})]
    groups = [(common, items_common, 216), (rare, items_rare, 80)]

    kb_json = sell_gear_main_keyboard(groups, 296)
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"sell_all_gear", "sell_rarity", "gear_detail", "appraiser_root"}
    rarity_labels = {
        b["action"]["label"] for b in buttons if b["action"].get("payload", {}).get("type") == "sell_rarity"
    }
    assert rarity_labels == {"Продать ⚪ ×12 — 216 зол.", "Продать 🟣 ×1 — 80 зол."}


def test_sell_gear_main_keyboard_rows_bounded_even_with_many_items() -> None:
    """Патч 35: сколько бы предметов ни было в редкости, экран не превышает
    лимит клавиатуры VK (10 строк) — группировка вместо кнопки на предмет."""
    all_rarities = ["common", "uncommon", "rare", "epic", "legendary"]
    groups = [
        (_rdef(rid, "⚪"), [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(20)], 100)
        for rid in all_rarities
    ]
    rows = _kb_rows(sell_gear_main_keyboard(groups, 500))
    assert len(rows) <= 10


def test_sell_gear_main_keyboard_empty_groups_has_only_back() -> None:
    kb_json = sell_gear_main_keyboard([], 0)
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"appraiser_root"}


# --- Патч 35/37: подробный режим с пагинацией ---


def test_sell_gear_detail_keyboard_is_not_inline_and_back_last() -> None:
    items = [Item(id=1, name="X", slot="weapon", base_stats={})]
    kb_json = sell_gear_detail_keyboard(items, page=1, total_pages=1)
    kb = json.loads(kb_json)
    assert kb["inline"] is False
    assert _last_button(kb_json)["action"]["payload"] == {"type": "appraiser_gear"}


def test_sell_gear_detail_keyboard_numbers_items_on_page() -> None:
    items = [Item(id=i, name=f"X{i}", slot="weapon", base_stats={}) for i in range(1, 4)]
    kb_json = sell_gear_detail_keyboard(items, page=1, total_pages=2)
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    numbered = [b for b in buttons if b["action"].get("payload", {}).get("type") == "sell_item"]
    assert [b["action"]["label"] for b in numbered] == ["1", "2", "3"]
    assert [b["action"]["payload"]["item"] for b in numbered] == [1, 2, 3]
    assert all(b["action"]["payload"]["page"] == 1 for b in numbered)


def test_sell_gear_detail_keyboard_pagination_buttons_respect_edges() -> None:
    items = [Item(id=1, name="X", slot="weapon", base_stats={})]

    first_page = json.loads(sell_gear_detail_keyboard(items, page=1, total_pages=3))
    labels = {b["action"]["label"] for row in first_page["buttons"] for b in row}
    assert "Стр. →" in labels
    assert "← Стр." not in labels

    last_page = json.loads(sell_gear_detail_keyboard(items, page=3, total_pages=3))
    labels = {b["action"]["label"] for row in last_page["buttons"] for b in row}
    assert "← Стр." in labels
    assert "Стр. →" not in labels


def test_sell_gear_detail_keyboard_rows_bounded_at_page_size() -> None:
    items = [Item(id=i, name="X", slot="weapon", base_stats={}) for i in range(GEAR_DETAIL_PAGE_SIZE)]
    rows = _kb_rows(sell_gear_detail_keyboard(items, page=1, total_pages=1))
    assert len(rows) <= 10


def test_sell_gear_detail_keyboard_empty_still_has_back() -> None:
    kb_json = sell_gear_detail_keyboard([], page=1, total_pages=1)
    buttons = [btn for row in _kb_rows(kb_json) for btn in row]
    payload_types = {b["action"]["payload"]["type"] for b in buttons if "payload" in b["action"]}
    assert payload_types == {"appraiser_gear"}


# --- Патч 35/37: предупреждение о продаже снаряжения лучше надетого ---


def test_sell_confirm_keyboard_is_not_inline() -> None:
    kb = json.loads(sell_confirm_keyboard({"type": "sell_rarity_confirm", "rarity": "rare"}))
    assert kb["inline"] is False


def test_sell_confirm_keyboard_carries_confirm_payload_and_cancel_to_gear_main() -> None:
    kb = json.loads(sell_confirm_keyboard({"type": "sell_rarity_confirm", "rarity": "rare"}))
    buttons = [btn for row in kb["buttons"] for btn in row]
    confirm = next(b for b in buttons if b["action"]["label"] == "Да, продать")
    assert confirm["action"]["payload"] == {"type": "sell_rarity_confirm", "rarity": "rare"}
    cancel = next(b for b in buttons if b["action"]["label"] == "Отмена")
    assert cancel["action"]["payload"] == {"type": "appraiser_gear"}
