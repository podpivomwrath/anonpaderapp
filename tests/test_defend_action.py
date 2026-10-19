"""«Защититься» (2026-10-19): добровольный пропуск хода за -10% входящего урона."""

import json

from bot.keyboards import combat_modes
from bot.keyboards.group_combat import group_combat_keyboard
from bot.keyboards.pvp import pvp_combat_keyboard
from bot.keyboards.raid import raid_combat_keyboard
from bot.keyboards.world import combat_keyboard
from game.combat import balance_config as bc
from game.combat.duel_engine import DuelEngine
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from tests.conftest import NoCritRng, combatant

ATTACK = lambda target: DeclaredAction(type=ActionType.ATTACK, target_id=target)  # noqa: E731
DEFEND = DeclaredAction(type=ActionType.DEFEND)


def _session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def _taken(defend: bool) -> tuple[int, list[str]]:
    a, b = combatant(1, side=0), combatant(2, side=1)
    actions = {2: ATTACK(1)}
    if defend:
        actions[1] = DEFEND
    result = resolve_tick(_session(a, b), actions, NoCritRng())
    return a.max_hp - a.current_hp, result.lines


def test_defend_cuts_incoming_damage_in_tick() -> None:
    plain, _ = _taken(defend=False)
    defended, lines = _taken(defend=True)
    assert defended == round(plain * (1 - bc.DEFEND_DAMAGE_REDUCTION)) or abs(
        defended - plain * (1 - bc.DEFEND_DAMAGE_REDUCTION)
    ) <= 1
    assert any("защищается" in line for line in lines)


def test_defend_deals_no_damage_and_wears_off() -> None:
    a, b = combatant(1, side=0), combatant(2, side=1)
    state = _session(a, b)
    resolve_tick(state, {1: DEFEND}, NoCritRng())
    assert b.current_hp == b.max_hp
    assert a.defend_reduction == 0.0  # снялась после тика


async def test_defend_protects_through_opponent_reply_in_duel() -> None:
    engine = DuelEngine(rng=NoCritRng())
    engine.start()
    try:
        a1, b1 = combatant(1, side=0), combatant(2, side=1)
        engine.start_duel(10, a1, b1)
        await engine.act(10, 1, ATTACK(2))
        await engine.act(10, 2, ATTACK(1))
        plain = a1.max_hp - a1.current_hp

        a2, b2 = combatant(3, side=0), combatant(4, side=1)
        engine.start_duel(20, a2, b2)
        await engine.act(20, 3, DEFEND)
        assert b2.current_hp == b2.max_hp
        await engine.act(20, 4, ATTACK(3))
        defended = a2.max_hp - a2.current_hp
        assert 0 < defended < plain
    finally:
        engine.shutdown()


def _buttons(keyboard_json: str) -> list[dict]:
    return [b["action"] for row in json.loads(keyboard_json)["buttons"] for b in row]


def test_every_combat_keyboard_has_defend_with_own_payload() -> None:
    keyboards = {
        combat_modes.SOLO_PVE: combat_keyboard("warrior", {}, "blood_knight"),
        combat_modes.PVP: pvp_combat_keyboard("warrior", {}, True, "blood_knight"),
        combat_modes.GROUP_PVE: group_combat_keyboard("warrior", {}, "blood_knight"),
        combat_modes.RAID: raid_combat_keyboard("warrior", {}, "blood_knight"),
    }
    payloads = set()
    for mode, kb in keyboards.items():
        rows = json.loads(kb)["buttons"]
        assert len(rows) <= 4 and all(len(r) <= 2 for r in rows)
        defend = [b for b in _buttons(kb) if b["label"] == combat_modes.DEFEND_LABEL]
        assert len(defend) == 1, mode.mode_id
        payload = defend[0]["payload"]
        payload = json.loads(payload) if isinstance(payload, str) else payload
        assert payload["type"] == mode.defend_payload
        payloads.add(payload["type"])
    assert len(payloads) == len(keyboards)
