"""Метка Разложения одна на цель от всех отравителей (2026-10-21, жалоба:
«два отравителя в пати друг другу метку не обновляют, а навык уходит в КД»)."""

import game.classes  # noqa: F401 - регистрация подклассов
from game.combat.session import EffectKind
from game.combat.subclass_skills import DECAY_TAG, SUBCLASS_SKILL_DEFS, _apply_vulnerability
from tests.conftest import combatant

DECAY = SUBCLASS_SKILL_DEFS["poisoner_decay"]


def _marks(target):
    return [e for e in target.effects if e.kind == EffectKind.VULNERABILITY]


def test_second_poisoner_refreshes_the_same_mark() -> None:
    target = combatant(9, side=1)
    _apply_vulnerability(target, DECAY, DECAY.effect_value, source_id=1)
    target.decay_debuffs()  # метка ослабла за ход
    mark = _marks(target)[0]
    mark.remaining_ticks = 1
    weakened = mark.value
    assert weakened < DECAY.effect_value

    _apply_vulnerability(target, DECAY, DECAY.effect_value, source_id=2)

    marks = _marks(target)
    assert len(marks) == 1 and marks[0].tag == DECAY_TAG
    assert marks[0].value == DECAY.effect_value  # снова полная сила
    assert marks[0].remaining_ticks == DECAY.effect_duration  # и свежая длительность
    assert marks[0].source_id == 2


def test_other_vulnerabilities_still_stack_with_the_mark() -> None:
    target = combatant(9, side=1)
    target.apply_effect(EffectKind.VULNERABILITY, 0.2, 2, source_id=5)  # печать мага
    _apply_vulnerability(target, DECAY, DECAY.effect_value, source_id=1)
    assert len(_marks(target)) == 2
