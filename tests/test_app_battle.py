"""Бой в приложении (2026-11-15): движок присылает снимок боя после старта и
каждого хода тем, у кого открыто приложение (bot/app_battle.py)."""

import asyncio

from bot import app_battle, app_channel
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
)
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from tests.conftest import NoCritRng, combatant


class _Ws:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_json(self, event: dict) -> None:
        self.events.append(event)


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_solo_battle_snapshots_go_to_the_app() -> None:
    vk_id = 5401
    ws = _Ws()
    app_channel.attach(vk_id, ws)
    try:
        engine = TickEngine(InMemoryActionStore(), rng=NoCritRng(), on_snapshot=app_battle.observer("solo"))
        state = CombatSessionState(session_id=vk_id, mode=CombatMode.PVE)
        state.add(combatant(1, side=0, name="Пупсик"))
        state.add(combatant(2, side=1, kind="mob", name="Волк", vitality=300))
        engine.start_session(state)
        await _settle()
        start = ws.events[-1]
        assert start["type"] == "battle" and start["engine"] == "solo" and start["turn"] == 1
        assert start["you"] == 1 and start["hits"] == [] and start["deadline"] is None
        me = next(c for c in start["combatants"] if c["id"] == 1)
        wolf = next(c for c in start["combatants"] if c["id"] == 2)
        assert "cooldowns" in me and "cooldowns" not in wolf and wolf["name"] == "Волк"

        await engine.declare_action(vk_id, 1, DeclaredAction(type=ActionType.ATTACK, target_id=2))
        await _settle()
        turn = ws.events[-1]
        assert turn["turn"] == 2 and not turn["finished"]
        hit = next(h for h in turn["hits"] if h["from"] == 1)
        assert hit["to"] == 2 and hit["amount"] > 0 and hit["hp_after"] < hit["hp_before"]
        assert next(c for c in turn["combatants"] if c["id"] == 2)["hp"] == hit["hp_after"]
    finally:
        app_channel.detach(vk_id, ws)


async def test_group_battle_finds_players_by_character_and_skips_others() -> None:
    in_app, in_vk = _Ws(), None
    app_channel.attach(5501, in_app, character_id=901)
    try:
        engine = TickEngine(InMemoryActionStore(), rng=NoCritRng(), on_snapshot=app_battle.observer("group"))
        state = CombatSessionState(session_id=-7, mode=CombatMode.PVE)
        state.add(combatant(901, side=0, name="В приложении"))
        state.add(combatant(902, side=0, name="Во ВКонтакте"))
        state.add(combatant(3, side=1, kind="mob", name="Волк", vitality=300))
        engine.start_session(state)
        await _settle()
        assert [e["you"] for e in in_app.events] == [901]
        assert app_battle.recipients("group", state) == {5501: 901}
        assert in_vk is None
    finally:
        app_channel.detach(5501, in_app)
    assert app_channel.vk_of_character(901) is None


async def test_nobody_in_app_nothing_built(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(app_battle, "payload", lambda *a: called.append(a))
    engine = TickEngine(InMemoryActionStore(), rng=NoCritRng(), on_snapshot=app_battle.observer("solo"))
    state = CombatSessionState(session_id=5601, mode=CombatMode.PVE)
    state.add(combatant(1, side=0))
    state.add(combatant(2, side=1, kind="mob"))
    engine.start_session(state)
    await _settle()
    assert called == []
