"""Затухание дебаффов (2026-10-16): три мага по очереди держали «Кровавую
печать» без перерыва, +70% урона по цели на весь бой. Теперь уязвимость и
ослабление слабеют на 30% за ход, новый такой же дебафф ложится от уже
ослабленной силы, полная сила - когда дебафф спал совсем."""

import pytest

from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from tests.conftest import NoCritRng, combatant

KEEP = 1 - bc.DEBUFF_DECAY_PER_TURN
SEAL = 0.35


def end_turn(c) -> None:
    """Конец хода так же, как в движках: тик длительностей, снятие, затухание."""
    for e in c.effects:
        e.remaining_ticks -= 1
    c.effects = [e for e in c.effects if e.remaining_ticks > 0]
    c.decay_debuffs()


def test_held_debuff_and_next_one_weaken():
    target = combatant(9, side=1)
    target.apply_effect(EffectKind.VULNERABILITY, SEAL, 3, source_id=1)
    end_turn(target)
    assert target.effect_total(EffectKind.VULNERABILITY) == pytest.approx(SEAL * KEEP)
    # Второй маг кладёт свою печать - уже от ослабленной силы.
    target.apply_effect(EffectKind.VULNERABILITY, SEAL, 3, source_id=2)
    assert target.effect_total(EffectKind.VULNERABILITY) == pytest.approx(2 * SEAL * KEEP)
    end_turn(target)
    assert target.effect_total(EffectKind.VULNERABILITY) == pytest.approx(2 * SEAL * KEEP ** 2)


def test_three_mages_cannot_hold_seventy_percent():
    """Ротация трёх печатей (2 хода каждая, по одной за ход) - раньше
    стабильные +70%, теперь затухает."""
    target = combatant(9, side=1)
    totals = []
    for turn in range(9):
        target.apply_effect(EffectKind.VULNERABILITY, SEAL, 2, source_id=1 + turn % 3)
        totals.append(target.effect_total(EffectKind.VULNERABILITY))
        end_turn(target)
    assert totals[1] < 0.70
    assert totals[-1] < 0.10


def test_full_strength_after_debuff_falls_off():
    target = combatant(9, side=1)
    target.apply_effect(EffectKind.WEAKEN, 0.3, 1, source_id=1)
    target.apply_effect(EffectKind.WEAKEN, 0.3, 2, source_id=2)
    end_turn(target)
    end_turn(target)
    assert not target.effects_of(EffectKind.WEAKEN)
    target.apply_effect(EffectKind.WEAKEN, 0.3, 2, source_id=1)
    assert target.effect_total(EffectKind.WEAKEN) == pytest.approx(0.3)


def test_negative_mob_trait_untouched():
    mob = combatant(9, side=1, kind="mob")
    mob.apply_effect(EffectKind.VULNERABILITY, -0.3, 5, source_id=9)
    end_turn(mob)
    assert mob.effect_total(EffectKind.VULNERABILITY) == pytest.approx(-0.3)


def test_resolver_decays_from_next_turn():
    """В бою (соло, группа, рейд, PvP-группа - один резолвер): в ход наложения
    дебафф в полной силе, со следующего - слабеет."""
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    player = combatant(1, side=0)
    enemy = combatant(2, side=1, vitality=500)
    state.add(player)
    state.add(enemy)
    skip = DeclaredAction(type=ActionType.SKIP)
    seal = DeclaredAction(type=ActionType.SKILL, skill_id="mage_blood_seal", target_id=2)
    resolve_tick(state, {1: seal, 2: skip}, NoCritRng())
    assert enemy.effect_total(EffectKind.VULNERABILITY) == pytest.approx(SEAL)
    resolve_tick(state, {1: skip, 2: skip}, NoCritRng())
    assert enemy.effect_total(EffectKind.VULNERABILITY) == pytest.approx(SEAL * KEEP)
