"""2026-10-19: пассивка Клинка теней - любой попавший удар с шансом вешает Метку."""

from types import SimpleNamespace

from game.combat import balance_config as bc
from game.combat import shared_rules
from game.combat.session import EffectKind
from tests.conftest import combatant


class _Rng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def _hit(**kw):
    base = dict(missed=False, is_dot=False, amount=50)
    base.update(kw)
    return SimpleNamespace(**base)


def test_passive_mark_only_for_shadow_blade_and_real_hits():
    blade = combatant(1, 0)
    blade.subclass_id = "shadow_blade"
    other = combatant(3, 0)
    target = combatant(2, 1)
    lines = []
    hit_roll = _Rng(bc.SHADOW_BLADE_PASSIVE_MARK_CHANCE / 2)
    shared_rules.passive_mark(other, target, _hit(), hit_roll, lines)
    shared_rules.passive_mark(blade, target, _hit(missed=True), hit_roll, lines)
    shared_rules.passive_mark(blade, target, _hit(is_dot=True), hit_roll, lines)
    shared_rules.passive_mark(blade, target, _hit(), _Rng(0.99), lines)
    assert target.effect_from(EffectKind.MARK, blade.id) is None
    shared_rules.passive_mark(blade, target, _hit(), hit_roll, lines)
    shared_rules.passive_mark(blade, target, _hit(), hit_roll, lines)
    assert target.effect_from(EffectKind.MARK, blade.id).stacks == 2
