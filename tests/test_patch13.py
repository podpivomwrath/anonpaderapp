"""Патч 13: редактируемые окна (ч.1), единый формат чисел (ч.2), убранный
флейвор-исход исследования (ч.3)."""

from bot import editable_message
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
        self._outer.next_id += 1
        return self._outer.next_id


class FakeBotApi:
    def __init__(self, edit_raises: bool = False) -> None:
        self.edit_calls: list[dict] = []
        self.send_calls: list[dict] = []
        self.edit_raises = edit_raises
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
