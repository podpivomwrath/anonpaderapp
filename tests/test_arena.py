"""Арена (2026-10-18): кнопка в таверне, бой без потерь, бой не виден на клетке."""

import asyncio
import json
from types import SimpleNamespace

from bot.handlers import arena, pvp
from bot.keyboards import arena as arena_kb
from bot.keyboards import world as world_kb
from game.combat.resolver import TickResult
from game.combat.session import CombatMode, CombatSessionState
from tests.conftest import combatant


def _labels(keyboard_json: str) -> list[list[str]]:
    rows = json.loads(keyboard_json)["buttons"]
    return [[b["action"].get("label") for b in row] for row in rows]


def test_arena_button_fits_tavern_limits():
    full = SimpleNamespace(level=60, subclass="guardian")
    rows = _labels(world_kb.tavern_keyboard(full))
    buttons = [b for row in rows for b in row if b and b != world_kb.BTN_SQUARE_BACK and "Персонаж" not in b]
    # 2026-10-21: +Наставник с площади - 7 кнопок, 4 ряда по 2.
    assert world_kb.BTN_ARENA in buttons and len(buttons) <= 7
    assert all(len(row) <= 2 for row in rows)


def test_arena_keyboards_are_small():
    assert sum(len(r) for r in _labels(arena_kb.arena_keyboard())) == 7
    assert _labels(arena_kb.arena_waiting_keyboard()) == [[arena_kb.BTN_ARENA_CANCEL]]


def test_arena_battle_is_not_visible_on_any_cell():
    battle = pvp.Battle(battle_type="mass", location=pvp.ARENA_LOCATION, arena=True)
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
        battle_type="mass", location=pvp.ARENA_LOCATION, arena=True,
        participants={
            1: pvp.Participant(1, 101, "Альфа", "warrior", "Воин"),
            2: pvp.Participant(2, 102, "Бета", "mage", "Маг"),
        },
        side_of={1: 0, 2: 1},
    )
    loser = combatant(2, side=1, name="Бета")
    loser.current_hp = 0
    battle.last_combatants = {1: combatant(1, side=0, name="Альфа"), 2: loser}
    pvp._battles[-778] = battle
    pvp._peer_battle[101] = pvp._peer_battle[102] = -778
    # Путь смерти/трофеев трогал бы БД - на арене до него дойти не должно.
    asyncio.run(pvp.on_mass_battle_finished(-778, TickResult(lines=[], deaths=[2])))
    assert 101 not in pvp._peer_battle and 102 not in pvp._peer_battle
    texts = dict(sent)
    assert "Победа на арене" in texts[101] and "Поражение на арене" in texts[102]
    assert all("Ничего не потеряно" in t for t in texts.values())


def test_code_is_removed_when_fight_starts(monkeypatch):
    started = []

    async def fake_start(db, a, ap, b, bp):
        started.append((ap, bp))

    monkeypatch.setattr(pvp, "start_arena_duel", fake_start)
    arena._codes["4321"] = (8, 808)
    arena._random_queue.append((9, 909))
    try:
        asyncio.run(arena._start(None, object(), 808, object(), 909))
        assert started == [(808, 909)]
        assert "4321" not in arena._codes and not arena.is_waiting(808) and not arena.is_waiting(909)
    finally:
        arena._codes.clear()
        arena._random_queue.clear()


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


def test_one_on_one_on_mass_engine_ends_like_a_duel(monkeypatch):
    """1×1 идёт на движке массового боя (2026-10-29), а итог - как у дуэли:
    все трофеи победителю."""
    from bot.handlers import pvp_results

    calls = []

    async def fake_finish(battle, winner, loser):
        calls.append((winner, loser))

    monkeypatch.setattr(pvp_results, "_finish_duel", fake_finish)
    battle = pvp.Battle(
        battle_type="mass", location=(5, 5),
        participants={
            1: pvp.Participant(1, 101, "Альфа", "warrior", "Воин"),
            2: pvp.Participant(2, 102, "Бета", "mage", "Маг"),
        },
        side_of={1: 0, 2: 1},
    )
    loser = combatant(2, side=1, name="Бета")
    loser.current_hp = 0
    battle.last_combatants = {1: combatant(1, side=0, name="Альфа"), 2: loser}
    pvp._battles[-779] = battle
    pvp._peer_battle[101] = pvp._peer_battle[102] = -779
    asyncio.run(pvp.on_mass_battle_finished(-779, TickResult(lines=[], deaths=[2])))
    assert calls == [(1, 2)]
    assert 101 not in pvp._peer_battle and 102 not in pvp._peer_battle


def test_stale_battle_mark_is_dropped():
    pvp._peer_battle[104] = -780
    assert pvp.drop_stale(104) and not pvp.has_active_battle(104)
    assert not pvp.drop_stale(104)
