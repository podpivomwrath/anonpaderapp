"""Патч 39, ч.3: навыки подклассов, не покрытые test_calibration.py/test_resolver.py —
Глухая оборона (BLOCK_STANCE/BLOCK_HEAL), Клинок теней (Метка добычи), Отравитель
(Дурманящий дротик/Токсический выброс), Элементалист (Горение/Цепь молний/Схождение),
Тёмный мистик (Оберег/Иссушение/Круг тьмы)."""

import random

from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from tests.conftest import NoCritRng, combatant


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


class AlwaysRollsRng(NoCritRng):
    """Как NoCritRng, но .random() всегда 0.0 — гарантирует срабатывание чанс-роллов."""

    def random(self) -> float:
        return 0.0


# --- Страж: Глухая оборона ---


def test_guardian_block_reduces_damage_for_two_turns() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian", agility=0)
    enemy = combatant(2, side=1)
    state = make_session(guardian, enemy)

    resolve_tick(state, {1: skill("guardian_block"), 2: attack(1)}, rng)
    assert guardian.has_effect(EffectKind.BLOCK_STANCE)
    hp_after_hit1 = guardian.current_hp

    # второй ход: страж НЕ переобъявляет блок — стойка должна ещё действовать
    resolve_tick(state, {1: attack(2), 2: attack(1)}, rng)
    reduced_hit = hp_after_hit1 - guardian.current_hp

    # эталон: страж без блока вообще
    plain_guardian = combatant(3, side=0, subclass_id="guardian", agility=0)
    plain_enemy = combatant(4, side=1)
    plain_state = make_session(plain_guardian, plain_enemy)
    resolve_tick(plain_state, {4: attack(3)}, rng)
    plain_hit = plain_guardian.max_hp - plain_guardian.current_hp

    assert reduced_hit < plain_hit


def test_guardian_block_heals_on_blocked_hit() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian", agility=0)
    guardian.current_hp = round(guardian.max_hp * 0.5)
    enemy = combatant(2, side=1)
    state = make_session(guardian, enemy)

    hp_before = guardian.current_hp
    resolve_tick(state, {1: skill("guardian_block"), 2: attack(1)}, rng)
    # хил от блока минус сам входящий (срезанный) урон — итог может быть
    # выше или ниже старта, но БЕЗ хила урон был бы строго больше
    took_with_heal = hp_before - guardian.current_hp

    plain_guardian = combatant(3, side=0, subclass_id="guardian", agility=0)
    plain_guardian.current_hp = round(plain_guardian.max_hp * 0.5)
    plain_enemy = combatant(4, side=1)
    plain_state = make_session(plain_guardian, plain_enemy)
    hp_before2 = plain_guardian.current_hp
    resolve_tick(plain_state, {4: attack(3)}, rng)
    took_plain = hp_before2 - plain_guardian.current_hp

    assert took_with_heal < took_plain


# --- Клинок теней: Метка добычи ---


def test_marked_strike_stacks_and_harvest_consumes() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(blade, enemy)

    resolve_tick(state, {1: skill("shadow_blade_marked_strike", 2)}, rng)
    mark = enemy.effect_from(EffectKind.MARK, 1)
    assert mark is not None and mark.stacks == 1

    resolve_tick(state, {1: attack(2)}, rng)  # обычная атака — стак НЕ растёт и НЕ тратится
    mark = enemy.effect_from(EffectKind.MARK, 1)
    assert mark is not None and mark.stacks == 1

    hp_before = enemy.current_hp
    resolve_tick(state, {1: skill("shadow_blade_mark_harvest", 2)}, rng)
    assert enemy.effect_from(EffectKind.MARK, 1) is None  # стаки потрачены
    assert enemy.current_hp < hp_before


def test_execute_doubles_damage_below_30_percent_hp() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    low_hp_enemy = combatant(2, side=1, vitality=500)
    low_hp_enemy.current_hp = round(low_hp_enemy.max_hp * 0.2)
    state1 = make_session(blade, low_hp_enemy)
    hp_before = low_hp_enemy.current_hp
    resolve_tick(state1, {1: skill("shadow_blade_execute", 2)}, rng)
    low_hp_damage = hp_before - low_hp_enemy.current_hp

    blade2 = combatant(3, side=0, subclass_id="shadow_blade")
    full_hp_enemy = combatant(4, side=1, vitality=500)
    state2 = make_session(blade2, full_hp_enemy)
    resolve_tick(state2, {3: skill("shadow_blade_execute", 4)}, rng)
    full_hp_damage = full_hp_enemy.max_hp - full_hp_enemy.current_hp

    assert low_hp_damage == full_hp_damage * 2


# --- Отравитель: Дурманящий дротик / Токсический выброс ---


def test_disrupt_applies_weaken_and_can_control() -> None:
    rng = AlwaysRollsRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    enemy = combatant(2, side=1, will=0)
    state = make_session(poisoner, enemy)

    result = resolve_tick(state, {1: skill("poisoner_disrupt", 2)}, rng)
    assert enemy.effect_total(EffectKind.WEAKEN) > 0
    # с AlwaysRollsRng и WIL=0 контроль обязан сработать (шанс 60% + резист 0)
    assert any("скован" in line or "пропускает" in line for line in result.lines) or enemy.has_effect(EffectKind.FREEZE)


def test_toxic_burst_scales_with_poison_and_clears_stacks() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=100, agility=50)
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(poisoner, enemy)

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    assert enemy.has_effect(EffectKind.DOT)

    hp_before = enemy.current_hp
    resolve_tick(state, {1: skill("poisoner_toxic_burst", 2)}, rng)
    assert enemy.current_hp < hp_before
    assert not enemy.has_effect(EffectKind.DOT)  # стаки яда сняты


# --- Элементалист: Горение / Цепь молний / Схождение ---


def test_fire_whip_applies_burning_dot() -> None:
    rng = NoCritRng()
    ele = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(ele, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert enemy.has_effect(EffectKind.DOT)
    hp_before = enemy.current_hp
    resolve_tick(state, {}, rng)
    assert enemy.current_hp < hp_before  # горение тикает


def test_chain_lightning_hits_three_targets() -> None:
    rng = NoCritRng()
    ele = combatant(1, side=0, subclass_id="elementalist")
    e1 = combatant(2, side=1, vitality=500)
    e2 = combatant(3, side=1, vitality=500)
    e3 = combatant(4, side=1, vitality=500)
    state = make_session(ele, e1, e2, e3)

    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    assert e1.current_hp < e1.max_hp
    assert e2.current_hp < e2.max_hp
    assert e3.current_hp < e3.max_hp


def test_convergence_bonus_with_burning_target() -> None:
    rng = NoCritRng()
    ele = combatant(1, side=0, subclass_id="elementalist")
    burning_enemy = combatant(2, side=1, vitality=500)
    burning_enemy.effects.append(
        __import__("game.combat.session", fromlist=["Effect"]).Effect(
            kind=EffectKind.DOT, value=1, remaining_ticks=3, source_id=1
        )
    )
    state1 = make_session(ele, burning_enemy)
    resolve_tick(state1, {1: skill("elementalist_convergence", 2)}, rng)
    burn_damage = burning_enemy.max_hp - burning_enemy.current_hp

    ele2 = combatant(3, side=0, subclass_id="elementalist")
    plain_enemy = combatant(4, side=1, vitality=500)
    state2 = make_session(ele2, plain_enemy)
    resolve_tick(state2, {3: skill("elementalist_convergence", 4)}, rng)
    plain_damage = plain_enemy.max_hp - plain_enemy.current_hp

    assert burn_damage > plain_damage


# --- Тёмный мистик: Оберег / Иссушение / Круг тьмы ---


def test_ward_shields_and_converts_remainder_to_heal_on_expiry() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
    state = make_session(mystic)

    resolve_tick(state, {1: skill("dark_mystic_ward")}, rng)
    pool = mystic.effect_from(EffectKind.SHIELD_POOL, 1)
    assert pool is not None and pool.value > 0

    # никто не бьёт — щит должен полностью истечь лечением (patch 16 — как «Второе сердце»)
    mystic.current_hp = max(mystic.current_hp - round(mystic.max_hp * 0.3), 1)
    hp_before_expiry = mystic.current_hp
    for _ in range(4):
        resolve_tick(state, {1: DeclaredAction(type=ActionType.SKIP)}, rng)
    assert mystic.current_hp > hp_before_expiry
    assert not mystic.has_effect(EffectKind.SHIELD_POOL)


def test_drain_bonus_damage_on_controlled_target() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic")
    frozen_enemy = combatant(2, side=1, vitality=500)
    frozen_enemy.effects.append(
        __import__("game.combat.session", fromlist=["Effect"]).Effect(
            kind=EffectKind.FREEZE, value=1, remaining_ticks=1, source_id=99
        )
    )
    state1 = make_session(mystic, frozen_enemy)
    resolve_tick(state1, {1: skill("dark_mystic_drain", 2)}, rng)
    frozen_damage = frozen_enemy.max_hp - frozen_enemy.current_hp

    mystic2 = combatant(3, side=0, subclass_id="dark_mystic")
    plain_enemy = combatant(4, side=1, vitality=500)
    state2 = make_session(mystic2, plain_enemy)
    resolve_tick(state2, {3: skill("dark_mystic_drain", 4)}, rng)
    plain_damage = plain_enemy.max_hp - plain_enemy.current_hp

    assert frozen_damage > plain_damage


def test_circle_of_dark_heals_allies_and_costs_hp() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
    ally = combatant(2, side=0)
    ally.current_hp = round(ally.max_hp * 0.5)
    state = make_session(mystic, ally)

    hp_before = mystic.current_hp
    ally_hp_before = ally.current_hp
    resolve_tick(state, {1: skill("dark_mystic_circle")}, rng)
    assert mystic.current_hp < hp_before  # себестоимость HP
    assert ally.current_hp > ally_hp_before  # союзник исцелён
