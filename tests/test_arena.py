"""Арена (2026-10-18): кнопка в таверне, бой без потерь, бой не виден на клетке."""

import asyncio
import json
from types import SimpleNamespace

from bot.handlers import arena, pvp
from bot.keyboards import arena as arena_kb
from bot.keyboards import world as world_kb
from game.combat.duel_engine import DuelResult


def _labels(keyboard_json: str) -> list[list[str]]:
    rows = json.loads(keyboard_json)["buttons"]
    return [[b["action"].get("label") for b in row] for row in rows]


def test_arena_button_fits_tavern_limits():
    full = SimpleNamespace(level=60, subclass="guardian")
    rows = _labels(world_kb.tavern_keyboard(full))
    buttons = [b for row in rows for b in row if b and b != world_kb.BTN_SQUARE_BACK and "Персонаж" not in b]
    assert world_kb.BTN_ARENA in buttons and len(buttons) <= 6
    assert all(len(row) <= 2 for row in rows)


def test_arena_keyboards_are_small():
    assert sum(len(r) for r in _labels(arena_kb.arena_keyboard())) == 4
    assert _labels(arena_kb.arena_waiting_keyboard()) == [[arena_kb.BTN_ARENA_CANCEL]]


def test_arena_battle_is_not_visible_on_any_cell():
    battle = pvp.Battle(battle_type="duel", location=pvp.ARENA_LOCATION, arena=True)
    pvp._battles[-777] = battle
    try:
        assert pvp._battles_at(*pvp.ARENA_LOCATION) == []
    finally:
        pvp._battles.pop(-777, None)


def test_arena_finish_skips_death_and_sends_both_back(monkeypatch):
    sent: list[tuple[int, str]] = []

    class Api:
        class messages:
            @staticmethod
            async def send(peer_id, message, random_id, keyboard=None):
                sent.append((peer_id, message))

    monkeypatch.setattr(arena, "_bot_api", Api)
    monkeypatch.setattr(pvp, "on_arena_finished", arena.on_arena_finished)
    battle = pvp.Battle(
        battle_type="duel", location=pvp.ARENA_LOCATION, arena=True,
        participants={
            1: pvp.Participant(1, 101, "Альфа", "warrior", "Воин"),
            2: pvp.Participant(2, 102, "Бета", "mage", "Маг"),
        },
        side_of={1: 0, 2: 1},
    )
    pvp._battles[-778] = battle
    pvp._peer_battle[101] = pvp._peer_battle[102] = -778
    # Путь смерти/трофеев трогал бы БД - на арене до него дойти не должно.
    asyncio.run(pvp.on_duel_finished(-778, DuelResult(finished=True, winner_id=1)))
    assert 101 not in pvp._peer_battle and 102 not in pvp._peer_battle
    texts = dict(sent)
    assert "Победа на арене" in texts[101] and "Поражение на арене" in texts[102]
    assert all("Ничего не потеряно" in t for t in texts.values())


def test_waiting_state_and_cancel():
    arena._random_queue.append((5, 505))
    arena._codes["1234"] = (6, 606)
    arena._entering.add(707)
    try:
        assert arena.is_waiting(505) and arena.is_waiting(606) and arena.is_waiting(707)
        for peer in (505, 606, 707):
            arena._leave_all(peer)
        assert not any(arena.is_waiting(p) for p in (505, 606, 707))
        assert "1234" not in arena._codes
    finally:
        arena._random_queue.clear()
        arena._codes.clear()
        arena._entering.clear()
