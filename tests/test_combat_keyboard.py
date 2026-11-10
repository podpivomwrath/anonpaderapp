"""ux-patch-7: боевая клавиатура прикрепляется ТОЛЬКО пока бой активен."""

import asyncio

import json

from bot.handlers import combat as ch
from game.combat.session import CombatMode, CombatSessionState
from game.combat.tick_engine import TickEngine, InMemoryActionStore
from tests.conftest import combatant


def _has_buttons(keyboard_json: str | None) -> bool:
    """Боевая клавиатура несёт кнопки; empty_keyboard() — пустой список."""
    if keyboard_json is None:
        return False
    return bool(json.loads(keyboard_json).get("buttons"))


class _CaptureApi:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []  # (первая строка, есть кнопки)

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        async def send(self, peer_id, message, random_id=0, keyboard=None):
            self._outer.sent.append((message.splitlines()[0], _has_buttons(keyboard)))

    @property
    def messages(self):
        return _CaptureApi._Messages(self)


def _setup(api) -> TickEngine:
    engine = TickEngine(InMemoryActionStore())
    ch.setup(engine, api)
    return engine


async def test_active_tick_has_combat_keyboard() -> None:
    api = _CaptureApi()
    engine = _setup(api)
    peer = 100
    ch._encounter_class[peer] = "warrior"
    ch._last_player_hp[peer] = 500
    state = CombatSessionState(session_id=peer, mode=CombatMode.PVE)
    state.add(combatant(ch.PLAYER_ID, side=0, kind="character", name="Т"))
    state.add(combatant(ch.MOB_ID, side=1, kind="mob", name="Моб", vitality=500))
    engine.sessions[peer] = state
    engine._resolve_locks[peer] = asyncio.Lock()

    from game.combat.resolver import TickResult

    await ch.on_tick_resolved(peer, 1, TickResult(finished=False))
    assert api.sent and api.sent[-1][1] is True  # бой активен → есть боевые кнопки


async def test_finishing_tick_has_no_combat_keyboard() -> None:
    api = _CaptureApi()
    engine = _setup(api)
    peer = 101
    ch._encounter_class[peer] = "warrior"
    ch._last_player_hp[peer] = 500
    state = CombatSessionState(session_id=peer, mode=CombatMode.PVE)
    state.add(combatant(ch.PLAYER_ID, side=0, kind="character", name="Т"))
    mob = combatant(ch.MOB_ID, side=1, kind="mob", name="Моб")
    mob.current_hp = 0  # моб мёртв — завершающий ход
    state.add(mob)
    engine.sessions[peer] = state
    engine._resolve_locks[peer] = asyncio.Lock()

    from game.combat.resolver import TickResult

    await ch.on_tick_resolved(peer, 1, TickResult(finished=True, winner_side=0))
    # лог финального удара — без кнопок вообще (мелькания боевых быть не должно)
    assert api.sent and api.sent[-1][1] is False
