"""Игрой управляют только кнопки и команды через «/» (2026-10-21, владелец)."""

import json
from types import SimpleNamespace

import pytest

from bot import button_gate
from bot.keyboards import world as kb
from models import PromoCode, User


def _msg(text, payload=None, peer=5001, state=None):
    return SimpleNamespace(text=text, payload=payload, peer_id=peer, from_id=peer, state_peer=state)


@pytest.fixture
def gate_db(monkeypatch, db_session):
    class Context:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *args): pass

    monkeypatch.setattr(button_gate, "get_session_factory", lambda: Context)
    return db_session


def test_every_text_button_carries_a_payload() -> None:
    raw = kb.movement_keyboard(5, 5, has_mount=True)
    for row in json.loads(raw)["buttons"]:
        for button in row:
            if button["action"]["type"] == "text":
                assert button["action"].get("payload"), button["action"]["label"]


async def test_typed_button_label_is_ignored(gate_db, make_character) -> None:
    c = await make_character()
    peer = (await gate_db.get(User, c.user_id)).vk_id
    assert not await button_gate.allowed(_msg(kb.BTN_EXPLORE, peer=peer))
    assert not await button_gate.allowed(_msg("привет", peer=peer))
    assert await button_gate.allowed(_msg(kb.BTN_EXPLORE, payload='{"btn":1}', peer=peer))
    assert await button_gate.allowed(_msg("/клава", peer=peer))
    assert await button_gate.allowed(_msg("/озеро", peer=peer))


async def test_typed_text_still_reaches_inputs_that_wait_for_it(gate_db, make_character, monkeypatch) -> None:
    from bot.handlers import turbo_ishak

    c = await make_character()
    peer = (await gate_db.get(User, c.user_id)).vk_id
    assert await button_gate.allowed(_msg("12:-4", peer=peer, state="MountCoordState:1"))
    monkeypatch.setattr(turbo_ishak, "_naming", {peer})
    assert await button_gate.allowed(_msg("Буцефал", peer=peer))
    monkeypatch.setattr(turbo_ishak, "_naming", set())
    gate_db.add(PromoCode(code="осень2026", created_by=1))
    await gate_db.flush()
    assert await button_gate.allowed(_msg("ОСЕНЬ2026", peer=peer))
    assert not await button_gate.allowed(_msg("зима", peer=peer))


async def test_new_player_and_group_chats_pass(gate_db) -> None:
    assert await button_gate.allowed(_msg("привет", peer=987654321))  # персонажа нет - онбординг
    chat = SimpleNamespace(text="Исследовать", payload=None, peer_id=2000000001, from_id=5, state_peer=None)
    assert await button_gate.allowed(chat)
