"""Откалиброванные механики подклассов (патч балансировки).

Включает регрессионный тест на баг, найденный в балансировочном тесте:
яд Отравителя по ошибке накладывался на атакующего вместо цели — симптом:
ДоТы «применяются» по логу, но противник урона не получает.
"""

import pytest

from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.content_loader import load_content
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


# --- Кровавый рыцарь: лайфстил ---


def test_lifesteal_heals_9_percent_of_damage() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.current_hp -= 100  # есть что лечить, но HP выше 50%
    enemy = combatant(2, side=1, vitality=500)  # жирный — переживёт удар
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * bc.BLOOD_KNIGHT_LIFESTEAL_BASE)


def test_lifesteal_bonus_below_half_hp() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.current_hp = knight.max_hp // 3  # ниже 50%
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    expected_ratio = bc.BLOOD_KNIGHT_LIFESTEAL_BASE + bc.BLOOD_KNIGHT_LIFESTEAL_LOW_HP_BONUS
    assert healed == round(damage_dealt * expected_ratio)


def test_lifesteal_capped_at_8_percent_max_hp() -> None:
    """Кап обязателен: без него лайфстил бесконтрольно скейлится."""
    rng = NoCritRng()
    # гигантский урон: высокий уровень + куча STR (12% от урона должно упереться в кап)
    knight = combatant(1, side=0, subclass_id="blood_knight", level=100, strength=2000)
    knight.current_hp = knight.max_hp // 3
    enemy = combatant(2, side=1, level=100, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    healed = knight.current_hp - hp_before
    assert healed == round(knight.max_hp * bc.BLOOD_KNIGHT_HEAL_CAP_PER_TICK)


# --- Отравитель: яд ---


def test_poison_lands_on_target_not_attacker() -> None:
    """РЕГРЕССИЯ (баг из балансировочного теста): яд — на цель, не на себя."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1)
    state = make_session(poisoner, enemy)

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    assert enemy.has_effect(EffectKind.DOT), "яд должен висеть на цели"
    assert not poisoner.has_effect(EffectKind.DOT), "яд НЕ должен висеть на атакующем"

    # и ДоТ реально наносит урон противнику на следующем тике
    hp_after_hit = enemy.current_hp
    resolve_tick(state, {}, rng)
    assert enemy.current_hp < hp_after_hit, "ДоТ обязан тикать по противнику"


def test_poison_scales_with_stats() -> None:
    """Сила яда масштабируется от статов: 0.60×WIL + 0.40×AGI на стак."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=100, agility=50)
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(poisoner, enemy)

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    hp_before_dot = enemy.current_hp
    resolve_tick(state, {}, rng)

    per_stack = (0.60 * 100 + 0.40 * 50) / bc.POISONER_MAX_STACKS  # 80/3
    assert hp_before_dot - enemy.current_hp == round(per_stack)


def test_poison_stacks_capped() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(poisoner, enemy)

    for _ in range(5):  # больше, чем макс. стаков
        resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    dots = enemy.effects_of(EffectKind.DOT)
    assert len(dots) == 1
    assert dots[0].stacks == bc.POISONER_MAX_STACKS


def test_poison_direct_hit_has_090_penalty() -> None:
    rng = NoCritRng()
    # эталон: обычная атака
    a1 = combatant(1, side=0, subclass_id="poisoner")
    b1 = combatant(2, side=1, vitality=500)
    s1 = make_session(a1, b1)
    resolve_tick(s1, {1: attack(2)}, rng)
    plain = b1.max_hp - b1.current_hp

    a2 = combatant(3, side=0, subclass_id="poisoner")
    b2 = combatant(4, side=1, vitality=500)
    s2 = make_session(a2, b2)
    resolve_tick(s2, {3: skill("poisoner_venom", 4)}, rng)
    poisoned_hit = b2.max_hp - b2.current_hp

    assert poisoned_hit == round(plain * bc.POISONER_DIRECT_MULT)


# --- Тёмный мистик: Кровавый пакт ---


def test_blood_pact_damage_is_076_of_attack() -> None:
    rng = NoCritRng()
    a1 = combatant(1, side=0, subclass_id="dark_mystic")
    b1 = combatant(2, side=1, vitality=500)
    s1 = make_session(a1, b1)
    resolve_tick(s1, {1: attack(2)}, rng)
    plain = b1.max_hp - b1.current_hp

    a2 = combatant(3, side=0, subclass_id="dark_mystic")
    b2 = combatant(4, side=1, vitality=500)
    s2 = make_session(a2, b2)
    resolve_tick(s2, {3: skill("dark_mystic_blood_pact", 4)}, rng)
    pact = b2.max_hp - b2.current_hp

    assert pact == round(plain * bc.DARK_MYSTIC_PACT_MULT)


def test_blood_pact_heals_lowest_hp_ally() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
    healthy_ally = combatant(2, side=0)
    wounded_ally = combatant(3, side=0)
    wounded_ally.current_hp = wounded_ally.max_hp // 4  # наименьший % HP
    enemy = combatant(4, side=1, vitality=500)
    state = make_session(mystic, healthy_ally, wounded_ally, enemy)

    hp_before = wounded_ally.current_hp
    resolve_tick(state, {1: skill("dark_mystic_blood_pact", 4)}, rng)

    damage = enemy.max_hp - enemy.current_hp
    conversion = 0.005 * 100 * bc.DARK_MYSTIC_HEAL_CONVERSION_COEF + bc.DARK_MYSTIC_HEAL_CONVERSION_BASE
    assert wounded_ally.current_hp - hp_before == round(damage * conversion)
    assert healthy_ally.current_hp == healthy_ally.max_hp  # хил ушёл раненому


def test_blood_pact_heals_self_without_allies() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic")
    mystic.current_hp = mystic.max_hp // 2
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(mystic, enemy)

    hp_before = mystic.current_hp
    resolve_tick(state, {1: skill("dark_mystic_blood_pact", 2)}, rng)
    assert mystic.current_hp > hp_before  # без союзников лечит себя


# --- Контент: откалиброванные значения баффов ---


def test_calibrated_guardian_buff_values_in_content() -> None:
    buffs = load_content().buffs
    assert buffs["guardian_bulwark"].stat_modifiers["full_block_chance"] == 0.25
    assert buffs["guardian_retribution"].stat_modifiers["counterstrike_mult"] == 0.70
    assert buffs["guardian_vital_block"].stat_modifiers["heal_on_block_pct_max_hp"] == 0.08
    assert buffs["guardian_heavy_hand"].stat_modifiers["damage_bonus"] == 0.10
    assert buffs["guardian_passive_stamina"].stat_modifiers["self_heal_per_tick_pct_max_hp"] == 0.025
    assert buffs["blood_knight_blood_rage"].stat_modifiers["damage_bonus"] == 0.05
