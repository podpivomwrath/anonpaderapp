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


# --- Кровавый рыцарь: лайфстил (патч 39, ч.3; урезано патчем 44, вектор
# нерфа сменён на урон патчем 45, ч.2 — см. content/skills/subclass_skills.json
# / game/combat/balance_config.py) ---


def test_lifesteal_heals_20_percent_of_damage() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.current_hp -= 100  # есть что лечить
    enemy = combatant(2, side=1, vitality=500)  # жирный — переживёт удар
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.2)


def test_lifesteal_capped_at_10_percent_max_hp() -> None:
    """Кап обязателен: без него лайфстил бесконтрольно скейлится (патч 44:
    общий кап для ВСЕХ навыков лайфстила, не только Кровопуска)."""
    rng = NoCritRng()
    # гигантский урон: высокий уровень + куча STR — лайфстил должен упереться в кап
    knight = combatant(1, side=0, subclass_id="blood_knight", level=100, strength=2000)
    knight.current_hp = knight.max_hp // 3
    enemy = combatant(2, side=1, level=100, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    healed = knight.current_hp - hp_before
    assert healed == round(knight.max_hp * bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)


def test_blood_seal_boosts_lifesteal_on_marked_target() -> None:
    """Кровавая печать: лайфстил последующей атаки рыцаря по цели усилен
    BLOOD_KNIGHT_BLOOD_SEAL_MULT (патч 44: x2 -> x1.5; патч 45, ч.2: x1.5 -> x1.75)."""
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.current_hp = round(knight.max_hp * 0.7)  # есть что лечить, но жив
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)

    resolve_tick(state, {1: skill("blood_knight_blood_seal", 2)}, rng)
    assert enemy.has_effect(EffectKind.BLOOD_SEAL)

    hp_before_hp = knight.current_hp
    enemy_hp_before = enemy.current_hp
    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy_hp_before - enemy.current_hp
    healed = knight.current_hp - hp_before_hp
    expected = min(round(damage_dealt * 0.2 * bc.BLOOD_KNIGHT_BLOOD_SEAL_MULT), round(knight.max_hp * bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN))
    assert healed == expected


def test_crimson_feast_heal_log_shows_isolated_positive_heal() -> None:
    """Патч 45, ч.1 (баг-репорт): себестоимость HP Багрового пира (прямая
    мутация current_hp ДО применения хилов/хитов хода) не должна попадать в
    дельту лога лечения — раньше строка "восполняет кровью" сравнивала HP на
    старте хода с итоговым HP, показывая знак себестоимости пополам с хилом
    ("-11 HP" при капнутом положительном лечении). Берём актёра почти на
    полном HP — себестоимость (15% ТЕКУЩЕГО) там заведомо больше капа
    лечения (10% МАКСИМУМА), так что итоговый HP актёра всё равно падает, но
    строка лога обязана показывать положительную (или ровно капнутую) дельту
    лечения, а не общий отрицательный результат хода."""
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight", level=100, strength=2000)
    enemy = combatant(2, side=1, level=100, vitality=500)
    state = make_session(knight, enemy)

    result = resolve_tick(state, {1: skill("blood_knight_crimson_feast", 2)}, rng)
    heal_line = next(line for line in result.lines if "восполняет кровью" in line)
    cap = round(knight.max_hp * bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)
    assert f"+{cap} HP" in heal_line  # ровно капнутое лечение, без знака себестоимости


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


# --- Тёмный мистик: Кровавый пакт (патч 39, ч.3) ---


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
    assert wounded_ally.current_hp - hp_before == round(damage * 0.7)
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
    assert buffs["blood_knight_blood_rage"].stat_modifiers["damage_bonus"] == 0.05
