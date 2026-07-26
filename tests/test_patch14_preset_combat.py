"""Патч 14, ч.3: применение stat_modifiers активного пресета в бою."""

import random

from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.combat.skills import outgoing_multiplier
from tests.conftest import combatant


class AlwaysLowRng(random.Random):
    """rng.random() всегда 0.0 — гарантирует срабатывание любых chance-роллов."""

    def random(self) -> float:
        return 0.0

    def choice(self, seq):
        return seq[0]


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def skill(skill_id: str, target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def test_damage_bonus_increases_outgoing_multiplier() -> None:
    attacker = combatant(1, side=0)
    target = combatant(2, side=1)
    base_mult = outgoing_multiplier(attacker, target)
    attacker.buff_modifiers = {"damage_bonus": 0.10}
    boosted_mult = outgoing_multiplier(attacker, target)
    assert boosted_mult == base_mult * 1.10


def test_guardian_full_block_chance_negates_almost_all_damage() -> None:
    """block_reduction сбрасывается reset_transient в конце тика — проверяем
    результат (урон от атаки моба почти нулевой — только пол в 1 из compute_hit,
    а не сам transient-флаг после тика). Сравниваем с базовым блоком без баффа."""
    rng = AlwaysLowRng()

    plain_guardian = combatant(1, side=0, subclass_id="guardian")
    plain_mob = combatant(2, side=1, kind="mob")
    resolve_tick(make_session(plain_guardian, plain_mob), {1: skill("guardian_block", 2)}, rng)
    plain_loss = plain_guardian.max_hp - plain_guardian.current_hp

    full_guardian = combatant(3, side=0, subclass_id="guardian")
    full_guardian.buff_modifiers = {"full_block_chance": 1.0}
    full_mob = combatant(4, side=1, kind="mob")
    resolve_tick(make_session(full_guardian, full_mob), {3: skill("guardian_block", 4)}, rng)
    full_block_loss = full_guardian.max_hp - full_guardian.current_hp

    assert full_block_loss <= 1  # только пол в 1 урон (max(round(base), 1) в compute_hit)
    assert full_block_loss < plain_loss


def test_guardian_heal_on_block_heals_self() -> None:
    rng = AlwaysLowRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {"heal_on_block_pct_max_hp": 0.5}
    guardian.current_hp = 1  # почти мёртв — чтобы увидеть исцеление
    mob = combatant(2, side=1, kind="mob")
    session = make_session(guardian, mob)

    resolve_tick(session, {1: skill("guardian_block", 2)}, rng)
    assert guardian.current_hp > 1


def test_guardian_counterstrike_hits_enemy() -> None:
    rng = AlwaysLowRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {"counterstrike_mult": 0.7}
    mob = combatant(2, side=1, kind="mob")
    mob_hp_before = mob.current_hp
    session = make_session(guardian, mob)

    resolve_tick(session, {1: skill("guardian_block", 2)}, rng)
    assert mob.current_hp < mob_hp_before  # контрудар нанёс урон
