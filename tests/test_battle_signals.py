"""Сигнал союзникам в групповом бою (2026-11-11): bot/battle_signals.py."""

import json
from types import SimpleNamespace

import pytest

from bot import battle_signals as bs
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
)
from tests.conftest import combatant


class FakeApi:
    def __init__(self, refuse=()):
        self.sent = []
        self.refuse = set(refuse)
        self.messages = self

    async def send(self, peer_id, message, random_id=0, **kw):
        if peer_id in self.refuse:
            raise RuntimeError("901")
        self.sent.append((peer_id, message))
        return 1


@pytest.fixture(autouse=True)
def _clean():
    bs._pending.clear()
    bs._no_out.clear()
    bs._no_in.clear()
    yield
    bs._pending.clear()
    bs._no_out.clear()
    bs._no_in.clear()


def _battle():
    """Двое игроков против моба: бойцы 1 и 2 - на стороне 0, peer 101 и 102."""
    me, ally = combatant(1, 0, name="Вася"), combatant(2, 0, name="Петя")
    mob = combatant(10, 1, kind="mob", name="Хор бойниц")
    state = CombatSessionState(session_id=7, mode=CombatMode.PVE)
    for c in (me, ally, mob):
        state.add(c)
    engine = SimpleNamespace(sessions={7: state})
    battle = SimpleNamespace(participants={1: SimpleNamespace(peer_id=101), 2: SimpleNamespace(peer_id=102)})
    return engine, battle, state


def _skill(sid, target=10):
    return DeclaredAction(type=ActionType.SKILL, skill_id=sid, target_id=target)


def test_action_text_names_skill_and_target() -> None:
    *_rest, state = _battle()
    combatants = state.combatants
    assert bs.action_text("Вася", _skill("warrior_stagger"), combatants) == "📢 Вася готовит «Оглушающий натиск» → Хор бойниц"
    # защитный навык сам выбирает, кого прикрыть - цели в сигнале нет
    assert bs.action_text("Вася", _skill("guardian_block"), combatants) == "📢 Вася готовит «Глухая оборона»"
    assert bs.action_text("Вася", DeclaredAction(type=ActionType.DEFEND), combatants) == "📢 Вася защищается"
    assert bs.action_text("Вася", DeclaredAction(type=ActionType.SKIP), combatants) is None


async def test_button_sends_each_ally_a_message() -> None:
    engine, battle, _state = _battle()
    kb = bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None)
    labels = [b["action"]["label"] for row in json.loads(kb)["buttons"] for b in row]
    assert bs.BTN in labels
    api = FakeApi()
    text, after = await bs.send(api, 101)
    assert api.sent == [(102, "📢 Вася готовит «Оглушающий натиск» → Хор бойниц")]
    assert "видят" in text and after is None  # клавиатура ожидания была пустой
    # второй раз - уже нечего
    text, _ = await bs.send(api, 101)
    assert "прошёл" in text and len(api.sent) == 1


async def test_stale_turn_is_not_sent() -> None:
    engine, battle, state = _battle()
    bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None)
    state.tick_number += 1  # ход уже резолвнулся
    api = FakeApi()
    text, _ = await bs.send(api, 101)
    assert "прошёл" in text and api.sent == []


async def test_settings_out_and_in() -> None:
    engine, battle, _state = _battle()
    bs.set_flags(101, {bs.OUT_FLAG: True})
    assert bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None) is None  # без кнопки
    bs.set_flags(101, {})
    bs.set_flags(102, {bs.IN_FLAG: True})
    bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None)
    api = FakeApi()
    text, _ = await bs.send(api, 101)
    assert api.sent == [] and "выключили" in text


def test_no_button_without_live_allies() -> None:
    engine, battle, state = _battle()
    state.combatants[2].current_hp = 0
    assert bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None) is None


def test_enemies_in_pvp_do_not_get_signal() -> None:
    engine, battle, state = _battle()
    state.combatants[2].side = 1  # «союзник» на самом деле враг
    assert bs.waiting_keyboard(engine, 7, battle, 1, _skill("warrior_stagger"), None) is None
