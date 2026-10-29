"""Комната арены (2026-10-29): вход по коду, стороны, старт у хозяина, итог по
сторонам, роспуск при уходе хозяина. Бесплатные зелья - Дар первопроходцев."""

import asyncio
import json
from types import SimpleNamespace

from bot.handlers import arena, pvp
from bot.keyboards import arena as arena_kb
from game.combat.resolver import TickResult
from game.economy import prerelease_config
from tests.conftest import combatant


class _Api:
    sent: list[tuple[int, str]] = []

    class messages:
        @staticmethod
        async def send(peer_id, message, random_id, keyboard=None):
            _Api.sent.append((peer_id, message))


class _Msg:
    def __init__(self, peer, text=""):
        self.peer_id = self.from_id = peer
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text, **_):
        self.answers.append(text)


def _labels(keyboard_json):
    return [b["action"]["label"] for row in json.loads(keyboard_json)["buttons"] for b in row]


def _char(cid, name):
    return SimpleNamespace(id=cid, name=name, screen=arena.SCREEN)


def _setup(monkeypatch):
    _Api.sent = []
    monkeypatch.setattr(arena, "_bot_api", _Api)
    chars = {101: _char(1, "Альфа"), 102: _char(2, "Бета"), 103: _char(3, "Гамма")}

    async def fake_arena_character(message):
        return chars.get(message.peer_id)

    monkeypatch.setattr(arena, "_arena_character", fake_arena_character)
    return chars


def _cleanup():
    arena._rooms.clear()
    arena._room_of.clear()
    arena._entering.clear()


def test_room_join_sides_and_host_leave(monkeypatch):
    chars = _setup(monkeypatch)
    try:
        asyncio.run(arena.create_room(_Msg(101)))
        code = arena._room_of[101]
        room = arena._rooms[code]
        assert arena.is_waiting(101)
        # Вход тем же вводом кода, что и у дуэли.
        arena._entering.add(102)
        asyncio.run(arena._join_room(_Msg(102), chars[102], room))
        asyncio.run(arena._join_room(_Msg(103), chars[103], room))
        sides = {peer: s for peer, (_, _, s) in room.members.items()}
        assert sides[101] == 0 and sides[102] == 1  # новичок - туда, где меньше
        asyncio.run(arena.pick_side(_Msg(103, arena_kb.BTN_ROOM_SIDE_2)))
        assert room.members[103][2] == 1
        start = arena_kb.BTN_ROOM_START
        assert start in _labels(arena.keyboard_for(101)) and start not in _labels(arena.keyboard_for(102))
        assert start in _labels(arena.keyboard_for_character(1))
        # Ушёл не хозяин - комната живёт; ушёл хозяин - распущена.
        asyncio.run(arena._leave_and_tell(103))
        assert code in arena._rooms and 103 not in arena._room_of
        asyncio.run(arena._leave_and_tell(101))
        assert code not in arena._rooms and not arena._room_of
        assert any("распускает" in t for p, t in _Api.sent if p == 102)
    finally:
        _cleanup()


def test_room_start_needs_both_sides_and_finish_keeps_room(monkeypatch):
    chars = _setup(monkeypatch)
    started = []

    async def fake_ready(db, cid, peer):
        return next(c for c in chars.values() if c.id == cid)

    async def fake_start(db, roster, code):
        started.append(sorted((c.id, s) for c, _, s in roster))

    class _Db:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(arena, "_ready", fake_ready)
    monkeypatch.setattr(arena, "get_session_factory", lambda: (lambda: _Db()))
    monkeypatch.setattr(pvp, "start_arena_room", fake_start)
    try:
        asyncio.run(arena.create_room(_Msg(101)))
        room = arena._rooms[arena._room_of[101]]
        host = _Msg(101)
        asyncio.run(arena.start_room(host))
        assert not started and "на каждой стороне" in host.answers[-1]
        asyncio.run(arena._join_room(_Msg(102), chars[102], room))
        asyncio.run(arena.start_room(_Msg(102)))  # не хозяин - молчит
        assert not started
        asyncio.run(arena.start_room(_Msg(101)))
        assert started == [[(1, 0), (2, 1)]] and room.fighting

        battle = pvp.Battle(
            battle_type="mass", location=pvp.ARENA_LOCATION, arena=True, arena_room=room.code,
            participants={1: pvp.Participant(1, 101, "Альфа", "warrior", "Воин"),
                          2: pvp.Participant(2, 102, "Бета", "mage", "Маг")},
            side_of={1: 0, 2: 1},
        )
        dead = combatant(1, side=0, name="Альфа")
        dead.current_hp = 0
        battle.last_combatants = {1: dead, 2: combatant(2, side=1, name="Бета")}
        pvp._battles[-901] = battle
        pvp._peer_battle[101] = pvp._peer_battle[102] = -901
        monkeypatch.setattr(pvp, "on_arena_finished", arena.on_arena_finished)
        asyncio.run(pvp.on_mass_battle_finished(-901, TickResult(lines=[], deaths=[1])))
        texts = dict(_Api.sent)
        assert "Победила сторона 2: Бета" in texts[101] and "ещё раз" in texts[102]
        assert not room.fighting and room.code in arena._rooms
    finally:
        _cleanup()


def test_free_arena_elixirs_follow_pioneer_gift(monkeypatch):
    assert prerelease_config.arena_free_elixirs()
    assert any("Арена" in line for line in prerelease_config.card()["lines"])
    monkeypatch.setattr(prerelease_config, "ACTIVE", False)
    assert not prerelease_config.arena_free_elixirs()
    assert "эликсиры не тратятся" in arena._arena_text()
