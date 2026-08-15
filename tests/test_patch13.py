"""Патч 13: редактируемые окна (ч.1), единый формат чисел (ч.2), убранный
флейвор-исход исследования (ч.3)."""

import json

import bot.keyboards.world as world_kb
from bot import editable_message
from bot.keyboards.items import inventory_keyboard
from config import Settings
from game.combat import display
from game.world import flavor, world_config as wc
from models import Item
from services import item_service


# --- ч.1: bot/editable_message.py ---


class _FakeMessages:
    def __init__(self, outer) -> None:
        self._outer = outer

    async def edit(self, **kwargs) -> None:
        self._outer.edit_calls.append(kwargs)
        if self._outer.edit_raises:
            raise RuntimeError("сообщение недоступно для правки")

    async def send(self, **kwargs) -> int:
        self._outer.send_calls.append(kwargs)
        # Патч 33, баг 1: два НЕЗАВИСИМЫХ режима отказа VK — битый attachment
        # (напр. неверный photo_id) не должен ронять клавиатуру, а отклонённая
        # целиком клавиатура (патч 32, баг 5 — лимит строк) не должна зависеть
        # от attachment.
        if self._outer.send_raises_with_attachment and kwargs.get("attachment") is not None:
            raise RuntimeError("attachment отклонён VK")
        if self._outer.send_raises_with_keyboard and kwargs.get("keyboard") is not None:
            raise RuntimeError("клавиатура отклонена VK")
        self._outer.next_id += 1
        return self._outer.next_id


class FakeBotApi:
    def __init__(
        self, edit_raises: bool = False, send_raises_with_keyboard: bool = False,
        send_raises_with_attachment: bool = False,
    ) -> None:
        self.edit_calls: list[dict] = []
        self.send_calls: list[dict] = []
        self.edit_raises = edit_raises
        self.send_raises_with_keyboard = send_raises_with_keyboard
        self.send_raises_with_attachment = send_raises_with_attachment
        self.next_id = 100
        self.messages = _FakeMessages(self)


async def test_send_or_edit_first_call_sends_new_message() -> None:
    api = FakeBotApi()
    await editable_message.send_or_edit(api, "ns", 1, "текст", "kb")
    assert len(api.send_calls) == 1
    assert len(api.edit_calls) == 0
    editable_message.clear("ns", 1)


async def test_send_or_edit_second_call_edits_same_message() -> None:
    api = FakeBotApi()
    await editable_message.send_or_edit(api, "ns2", 1, "текст 1", "kb")
    await editable_message.send_or_edit(api, "ns2", 1, "текст 2", "kb")
    assert len(api.send_calls) == 1  # только первый раз
    assert len(api.edit_calls) == 1
    assert api.edit_calls[0]["message"] == "текст 2"
    editable_message.clear("ns2", 1)


async def test_send_or_edit_falls_back_to_send_when_edit_fails() -> None:
    api = FakeBotApi(edit_raises=True)
    await editable_message.send_or_edit(api, "ns3", 1, "текст 1", "kb")
    await editable_message.send_or_edit(api, "ns3", 1, "текст 2", "kb")
    assert len(api.send_calls) == 2  # edit упал — открыли новое взамен
    assert len(api.edit_calls) == 1
    editable_message.clear("ns3", 1)


async def test_send_or_edit_falls_back_without_keyboard_when_send_rejects_it() -> None:
    """Патч 32, баг 5: если VK отклоняет саму отправку с клавиатурой (напр.
    превышен лимит строк), игрок раньше не получал вообще НИЧЕГО — кнопка
    выглядела нерабочей без единого сообщения об ошибке. Клавиатура отклонена
    независимо от attachment — фолбэк без attachment (патч 33) тоже не
    помогает, доходим до голого текста третьей попыткой."""
    api = FakeBotApi(send_raises_with_keyboard=True)
    await editable_message.send_or_edit(api, "ns5", 1, "текст", "перегруженная kb")
    assert len(api.send_calls) == 3
    assert api.send_calls[0]["keyboard"] == "перегруженная kb"
    assert api.send_calls[1]["keyboard"] == "перегруженная kb"  # без attachment — тоже упало
    assert "keyboard" not in api.send_calls[2]
    editable_message.clear("ns5", 1)


async def test_send_or_edit_falls_back_without_attachment_keeps_keyboard() -> None:
    """Патч 33, баг 1: битый attachment (напр. неверный photo_id скупщика)
    НЕ должен ронять клавиатуру продажи заодно с картинкой — раньше единый
    фолбэк (патч 32) убирал и то, и другое при любом отказе VK, из-за чего
    игрок терял кнопки продажи только потому, что не загрузилась картинка."""
    api = FakeBotApi(send_raises_with_attachment=True)
    await editable_message.send_or_edit(api, "ns6", 1, "текст", "kb", attachment="photo-1_2")
    assert len(api.send_calls) == 2  # первая с attachment упала, вторая без — но с клавиатурой
    assert api.send_calls[0]["attachment"] == "photo-1_2"
    assert api.send_calls[1]["keyboard"] == "kb"
    assert "attachment" not in api.send_calls[1]
    editable_message.clear("ns6", 1)


async def test_clear_forces_new_message_next_time() -> None:
    api = FakeBotApi()
    await editable_message.send_or_edit(api, "ns4", 1, "текст 1", "kb")
    editable_message.clear("ns4", 1)
    await editable_message.send_or_edit(api, "ns4", 1, "текст 2", "kb")
    assert len(api.send_calls) == 2
    assert len(api.edit_calls) == 0
    editable_message.clear("ns4", 1)


async def test_namespaces_are_independent_per_peer() -> None:
    api = FakeBotApi()
    await editable_message.send_or_edit(api, "a", 1, "A", "kb")
    await editable_message.send_or_edit(api, "b", 1, "B", "kb")
    # разные namespace для одного peer_id — оба должны были ПОСЛАТЬ, не EDIT
    assert len(api.send_calls) == 2
    assert len(api.edit_calls) == 0
    editable_message.clear("a", 1)
    editable_message.clear("b", 1)


# --- Патч 32, баг 5: клавиатуры инвентаря/продажи снаряжения не превышают
# лимит VK на строки (10) — раньше при накопленных предметах messages.send/
# .edit падал с отклонённой клавиатурой и игрок не получал вообще ничего. ---


def _kb_rows(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


def test_inventory_keyboard_caps_rows_at_vk_limit(monkeypatch) -> None:
    """Патч 41: инвентарь — настоящая пагинация (6/стр., 2 в ряд), а не
    жёсткий срез в один длинный столбик — при любом размере инвентаря
    страница остаётся короткой."""
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    items = [
        (Item(id=i, name=f"Предмет {i}", slot="weapon", base_stats={}), False) for i in range(20)
    ]
    rows = _kb_rows(inventory_keyboard(items))
    assert len(rows) <= 10
    # 6 предметов/стр. по 2 в ряд = 3 ряда + [Стр. →] + [← Назад].
    assert len(rows) == 5


def test_inventory_keyboard_pagination_pages_through_items(monkeypatch) -> None:
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None))
    items = [
        (Item(id=i, name=f"Предмет {i}", slot="weapon", base_stats={}), False) for i in range(20)
    ]

    page1 = json.loads(inventory_keyboard(items, page=1))
    labels_p1 = {b["action"]["label"] for row in page1["buttons"] for b in row}
    assert "Предмет 0" in labels_p1
    assert "Предмет 6" not in labels_p1
    assert "Стр. →" in labels_p1
    assert "← Стр." not in labels_p1

    page2 = json.loads(inventory_keyboard(items, page=2))
    labels_p2 = {b["action"]["label"] for row in page2["buttons"] for b in row}
    assert "Предмет 6" in labels_p2
    assert "Предмет 0" not in labels_p2
    assert "← Стр." in labels_p2
    assert "Стр. →" in labels_p2

    last_page = json.loads(inventory_keyboard(items, page=99))  # за пределами — клампится
    labels_last = {b["action"]["label"] for row in last_page["buttons"] for b in row}
    assert "Предмет 19" in labels_last
    assert "Стр. →" not in labels_last


# --- ч.2: единый формат числовых дельт ---


def test_stat_delta_line_shows_only_changed_stats() -> None:
    old = Item(name="Старый", slot="weapon", base_stats={"str": 5})
    new = Item(name="Новый", slot="weapon", base_stats={"str": 8, "vit": 1})
    assert item_service.stat_delta_line(old, new) == "(Сила +3, Выносливость +1)"


def test_stat_delta_line_no_changes() -> None:
    old = Item(name="A", slot="weapon", base_stats={"str": 5})
    new = Item(name="B", slot="weapon", base_stats={"str": 5})
    assert item_service.stat_delta_line(old, new) == "(без изменений)"


def test_stat_delta_line_handles_none_old_item() -> None:
    new = Item(name="Новый", slot="weapon", base_stats={"str": 4})
    assert item_service.stat_delta_line(None, new) == "(Сила +4)"


def test_death_penalty_line_includes_percentage() -> None:
    text = flavor.death_penalty_line(124)
    assert "124" in text and "%" in text


# --- ч.3: убран флейвор как самостоятельный исход исследования ---


def test_explore_combat_chance_is_half_and_flavor_chance_removed() -> None:
    assert wc.EXPLORE_COMBAT_CHANCE == 0.5
    assert not hasattr(wc, "EXPLORE_FLAVOR_CHANCE")


def test_remarks_are_plain_strings_without_reward() -> None:
    assert all(isinstance(entry, str) for entry in flavor._REMARKS["remarks"])
    assert len(flavor._REMARKS["remarks"]) == 5


def test_remark_pick_returns_plain_text() -> None:
    import random

    text = flavor.remark_pick(random.Random(1))
    assert isinstance(text, str) and text
