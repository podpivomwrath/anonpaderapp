"""2026-10-17: от навыков игрок уклоняется с тем же коэффициентом и за счёт
эффектов/бафов, а не только ловкости. Обычная атака и мобы - как раньше."""

import random

from game.combat import balance_config as bc
from game.combat.session import EffectKind
from game.combat.skills import compute_hit
from tests.conftest import combatant


def _rate(target, is_ability: bool, n: int = 4000) -> float:
    attacker = combatant(1, 0)
    rng = random.Random(5)
    misses = sum(compute_hit(attacker, target, rng, is_ability=is_ability).missed for _ in range(n))
    return misses / n


def test_smoke_screen_counts_quarter_against_abilities():
    rogue = combatant(2, 1, agility=0)
    rogue.apply_effect(EffectKind.DODGE, 0.4, 2, rogue.id)
    assert abs(_rate(rogue, is_ability=True) - 0.4 * bc.EFFECT_ABILITY_DODGE_RATIO) < 0.03
    assert abs(_rate(rogue, is_ability=False) - 0.4) < 0.03


def test_mob_dodge_mechanic_is_untouched():
    mob = combatant(2, 1, kind="mob", agility=0)
    mob.apply_effect(EffectKind.DODGE, 0.4, 2, mob.id)
    assert abs(_rate(mob, is_ability=True) - 0.4) < 0.03
