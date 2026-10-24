"""Модель статов (2026-10-24): игра считает по CURRENT, и это ровно прежние
формулы. Другие модели подставляют только инструменты (tools/sim_stat_model.py)."""

import itertools

from game.combat import formulas, stat_model
from game.combat.session import Stats


def test_game_uses_game_rules() -> None:
    """2026-10-24: игра - на модели ребаланса, прежние формулы - CURRENT."""
    assert stat_model.ACTIVE is stat_model.GAME


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
    # Прибавки подкласса - только у модели игры (разбойникам вместо крита и уворота с Ловкости).
    assert stat_model.subclass_crit_bonus("shadow_blade") == 0.10
    assert stat_model.subclass_dodge_bonus("poisoner") == 0.05
    assert stat_model.subclass_crit_bonus("guardian") == 0.0
    assert stat_model.GAME.control_resist(50) == formulas.control_resist(50)


def test_hyper_has_diminishing_returns() -> None:
    m = stat_model.HyperModel()
    gains = [m.crit_chance(Stats(agility=a)) for a in (0, 100, 200, 300)]
    steps = [b - a for a, b in itertools.pairwise(gains)]
    assert steps[0] > steps[1] > steps[2] > 0
    assert gains[-1] < m.crit_cap


def test_current_primary_is_linear() -> None:
    for v in (0, 50, 150, 400):
        assert stat_model.CURRENT.primary_value(v, 60, True) == v
    d = stat_model.HyperModel(primary_over=0.5)
    assert d.primary_value(130, 50, True) == 130
    assert d.primary_value(230, 50, True) == 180
    assert d.primary_value(230, 50, False) == 230  # мобов не трогает
