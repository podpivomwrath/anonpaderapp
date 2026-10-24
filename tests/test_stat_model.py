"""Модель статов (2026-10-24): игра считает по CURRENT, и это ровно прежние
формулы. Другие модели подставляют только инструменты (tools/sim_stat_model.py)."""

import itertools

from game.combat import formulas, stat_model
from game.combat.session import Stats


def test_game_uses_current_rules() -> None:
    assert stat_model.ACTIVE is stat_model.CURRENT


def test_current_equals_old_formulas() -> None:
    for v in (0, 1, 15, 50, 100, 167, 200, 250, 400):
        s = Stats(strength=v, agility=v, intellect=v, vitality=v, will=v)
        m = stat_model.CURRENT
        assert m.crit_chance(s) == formulas.crit_chance(v)
        assert m.dodge(s, False) == formulas.dodge_chance(v)
        assert m.dodge(s, True) == formulas.ability_dodge_chance(v)
        assert m.mitigation(s) == formulas.mitigation(v)
        assert m.control_resist(v) == formulas.control_resist(v)
        assert m.support_power(s) == formulas.support_power(v)
        assert m.crit_multiplier_bonus(s) == 0.0 and m.effect_power(s) == 1.0
    assert stat_model.subclass_crit_bonus("shadow_blade") == 0.0
    assert stat_model.subclass_dodge_bonus("shadow_blade") == 0.0


def test_hyper_has_diminishing_returns() -> None:
    m = stat_model.HyperModel()
    gains = [m.crit_chance(Stats(agility=a)) for a in (0, 100, 200, 300)]
    steps = [b - a for a, b in itertools.pairwise(gains)]
    assert steps[0] > steps[1] > steps[2] > 0
    assert gains[-1] < m.crit_cap
