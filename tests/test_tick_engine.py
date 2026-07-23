"""Тиковый движок: PvE без таймера, PvP-таймер + досрочный резолв."""

import asyncio

import pytest

from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from tests.conftest import NoCritRng, combatant


def make_state(mode: CombatMode, *combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode)
    for c in combatants:
        state.add(c)
    return state


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


class Recorder:
    def __init__(self) -> None:
        self.ticks: list[tuple[int, int, TickResult]] = []
        self.finished: list[tuple[int, TickResult]] = []
        self.tick_event = asyncio.Event()

    async def on_tick(self, session_id: int, tick: int, result: TickResult) -> None:
        self.ticks.append((session_id, tick, result))
        self.tick_event.set()

    async def on_finish(self, session_id: int, result: TickResult) -> None:
        self.finished.append((session_id, result))


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


def make_engine(recorder: Recorder, window: float = 60.0) -> TickEngine:
    return TickEngine(
        InMemoryActionStore(),
        pvp_window_seconds=window,
        rng=NoCritRng(),
        on_tick_resolved=recorder.on_tick,
        on_battle_finished=recorder.on_finish,
    )


async def test_pve_waits_for_all_players(recorder: Recorder) -> None:
    """PvE: без таймера, тик ждёт всех живых игроков."""
    engine = make_engine(recorder)
    p1 = combatant(1, side=0)
    p2 = combatant(2, side=0)
    wolf = combatant(3, side=1, kind="mob", name="Волк", vitality=200)
    state = make_state(CombatMode.PVE, p1, p2, wolf)
    engine.start_session(state)

    await engine.declare_action(1, 1, attack(3))
    assert recorder.ticks == []  # один из двух — ждём

    await engine.declare_action(1, 2, attack(3))
    assert len(recorder.ticks) == 1  # оба объявили — резолв сразу, без таймера
    _, tick, result = recorder.ticks[0]
    assert tick == 1
    assert wolf.current_hp < wolf.max_hp
    assert state.tick_number == 2  # следующий тик открыт


async def test_pvp_early_resolve_when_all_declared(recorder: Recorder) -> None:
    """Общее правило PvP: все объявили раньше таймера — резолв досрочно."""
    engine = make_engine(recorder, window=3600)  # таймер заведомо не успеет
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    state = make_state(CombatMode.PVP_GROUP, a, b)
    engine.start()
    try:
        engine.start_session(state)
        await engine.declare_action(1, 1, attack(2))
        assert recorder.ticks == []
        await engine.declare_action(1, 2, attack(1))
        assert len(recorder.ticks) == 1  # досрочно, без ожидания часа
    finally:
        engine.shutdown()


async def test_pvp_timeout_skips_missing(recorder: Recorder) -> None:
    """Кто не успел за окно — пропускает ход."""
    engine = make_engine(recorder, window=0.3)
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    state = make_state(CombatMode.PVP_GROUP, a, b)
    engine.start()
    try:
        engine.start_session(state)
        await engine.declare_action(1, 1, attack(2))
        await asyncio.wait_for(recorder.tick_event.wait(), timeout=5)
    finally:
        engine.shutdown()

    _, _, result = recorder.ticks[0]
    assert any("пропускает" in line for line in result.lines)
    assert a.current_hp == a.max_hp       # б не походил — а не получил урона
    assert b.current_hp < b.max_hp


async def test_battle_finishes_and_session_removed(recorder: Recorder) -> None:
    engine = make_engine(recorder)
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    b.current_hp = 1
    state = make_state(CombatMode.PVP_GROUP, a, b)
    engine.start()
    try:
        engine.start_session(state)
        await engine.declare_action(1, 1, attack(2))
        await engine.declare_action(1, 2, attack(1))
    finally:
        engine.shutdown()

    assert recorder.finished
    _, result = recorder.finished[0]
    assert result.winner_side == 0
    assert 1 not in engine.sessions  # сессия удалена


async def test_duel_mode_rejected(recorder: Recorder) -> None:
    engine = make_engine(recorder)
    state = make_state(CombatMode.DUEL, combatant(1, side=0), combatant(2, side=1))
    with pytest.raises(ValueError):
        engine.start_session(state)


async def test_dead_player_cannot_declare(recorder: Recorder) -> None:
    engine = make_engine(recorder)
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    a.current_hp = 0
    state = make_state(CombatMode.PVP_GROUP, a, b)
    engine.start_session(state)
    with pytest.raises(ValueError):
        await engine.declare_action(1, 1, attack(2))
