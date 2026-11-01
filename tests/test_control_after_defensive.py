"""Контроль по тому, кто уже сходил защитным действием (2026-11-02, решение
владельца). Удар щитом, блок и «Защита» срабатывают в первой фазе хода, до
контроля, - сбивать уже нечего. Раньше контроль на этом сгорал и в логе
писалось «теряет ход», хотя Страж ударил. Теперь он переносится на следующий
ход цели."""

import random

from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from tests.conftest import combatant


class MidRng(random.Random):
    """0.5: дротик (60%) сбивает, без крита и уклонения."""

    def random(self) -> float:
        return 0.5

    def choice(self, seq):
        return seq[0]


def _duel():
    poisoner = combatant(1, side=0, name="Еста", subclass_id="poisoner", will=0)
    guardian = combatant(2, side=1, name="Страж", subclass_id="guardian", will=0, vitality=5000)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(guardian)
    state.tick_number = 1
    return state


def _tick(state, guardian_action: DeclaredAction):
    state.tick_number += 1
    return resolve_tick(state, {
        1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_disrupt", target_id=2),
        2: guardian_action,
    }, MidRng())


def test_control_on_shield_bash_moves_to_next_turn() -> None:
    state = _duel()
    first = _tick(state, DeclaredAction(type=ActionType.SKILL, skill_id="guardian_shield_bash", target_id=1))
    assert not any("Страж теряет ход" in line for line in first.lines)
    state.combatants[1].cooldowns.clear()
    second = resolve_tick(state, {
        1: DeclaredAction(type=ActionType.ATTACK, target_id=2),
        2: DeclaredAction(type=ActionType.ATTACK, target_id=1),
    }, MidRng())
    assert any("Страж теряет ход" in line for line in second.lines)
    assert not any(h.source_id == 2 for h in second.hits)


def test_control_on_attack_still_this_turn() -> None:
    state = _duel()
    result = _tick(state, DeclaredAction(type=ActionType.ATTACK, target_id=1))
    assert any("Страж теряет ход" in line for line in result.lines)
    assert not any(h.source_id == 2 for h in result.hits)
