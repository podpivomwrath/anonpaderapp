"""2026-10-18: две провокации не прикрывают Стражей друг другом и не
перемножаются; слабое Горение не гасит сильное от того же элементалиста."""

from game.combat.session import BURN_TAG, EffectKind
from game.combat.skills import outgoing_multiplier
from tests.conftest import combatant


def _provoked_enemy():
    enemy = combatant(10, 1)
    enemy.apply_effect(EffectKind.PROVOKE_PVP, 0.45, 2, 1)  # Страж 1 с Клеймом
    enemy.apply_effect(EffectKind.PROVOKE_PVP, 0.30, 2, 2)  # Страж 2
    return enemy


def test_hitting_any_provoking_guardian_is_full_damage():
    enemy = _provoked_enemy()
    base = outgoing_multiplier(enemy, combatant(99, 0))
    enemy_clean = combatant(11, 1)
    assert base < outgoing_multiplier(enemy_clean, combatant(99, 0))
    for guardian_id in (1, 2):
        assert outgoing_multiplier(enemy, combatant(guardian_id, 0)) == outgoing_multiplier(
            enemy_clean, combatant(guardian_id, 0)
        )


def test_two_provokes_do_not_multiply():
    enemy = _provoked_enemy()
    ally = combatant(3, 0)
    expected = outgoing_multiplier(combatant(11, 1), ally) * (1 - 0.45)
    assert abs(outgoing_multiplier(enemy, ally) - expected) < 1e-9


def test_weaker_burn_keeps_stronger_from_same_source():
    target = combatant(5, 1)
    target.apply_effect(EffectKind.DOT, 100.0, 3, 7, tag=BURN_TAG)
    target.apply_effect(EffectKind.DOT, 50.0, 3, 7, tag=BURN_TAG)
    (burn,) = target.effects_of(EffectKind.DOT)
    assert burn.value == 100.0
    target.apply_effect(EffectKind.DOT, 120.0, 3, 7, tag=BURN_TAG)
    assert target.effects_of(EffectKind.DOT)[0].value == 120.0
    target.apply_effect(EffectKind.DOT, 50.0, 3, 8, tag=BURN_TAG)  # другой элементалист - своё Горение
    assert len(target.effects_of(EffectKind.DOT)) == 2
