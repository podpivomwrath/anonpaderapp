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


# --- Элементалист: «Экономия»/«Перегрузка»/«Стихийный поток» (патч 46, ч.1) ---
# Переписаны с несуществующего расхода ресурса (маны нет, только КД) на
# реальные механики кулдауна/бонуса урона.


def test_thrift_full_chance_skips_cooldown() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist")
    caster.buff_modifiers["no_cooldown_chance"] = 1.0
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert not caster.is_on_cooldown("elementalist_fire")


def test_thrift_zero_chance_sets_cooldown_normally() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert caster.is_on_cooldown("elementalist_fire")


def test_overload_skips_cooldown_every_interval_turns() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist")
    caster.buff_modifiers["overload_active"] = 1.0
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)

    for _ in range(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS):
        resolve_tick(state, {1: attack(2)}, rng)
    assert caster.overload_ready

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert not caster.is_on_cooldown("elementalist_fire")
    assert not caster.overload_ready


def test_overload_inactive_without_buff() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)

    for _ in range(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS):
        resolve_tick(state, {1: attack(2)}, rng)
    assert not caster.overload_ready


def test_elemental_flow_triggers_on_three_distinct_elements() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["elemental_flow_bonus"] = 0.20
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert not caster.has_effect(EffectKind.ELEMENTAL_FLOW)
    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    assert not caster.has_effect(EffectKind.ELEMENTAL_FLOW)
    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    assert caster.has_effect(EffectKind.ELEMENTAL_FLOW)
    assert caster.effect_total(EffectKind.ELEMENTAL_FLOW) == 0.20
    assert caster.recent_elements == []  # цепь потрачена


def test_elemental_flow_repeated_element_resets_streak() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["elemental_flow_bonus"] = 0.20
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)  # повтор — не считается
    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    assert caster.has_effect(EffectKind.ELEMENTAL_FLOW)


# --- Контент: калиброванные значения микробаффов Элементалиста ---


def test_calibrated_elementalist_buff_values_in_content() -> None:
    buffs = load_content().buffs
    assert buffs["elementalist_thrift"].stat_modifiers["no_cooldown_chance"] == bc.ELEMENTALIST_ECONOMY_NO_COOLDOWN_CHANCE
    assert buffs["elementalist_overload"].stat_modifiers["overload_active"] == 1.0
    assert buffs["elementalist_elemental_flow"].stat_modifiers["elemental_flow_bonus"] == bc.ELEMENTALIST_ELEMENTAL_FLOW_BONUS


# --- Патч 47: «Оцепенение»/«Глубокая заморозка»/«Затяжной яд»/«Несгибаемый» —
# ещё 4 микробаффа-заглушки, не действовавшие в бою. Плюс баг 2 (дубль строки
# "ход потерян") и баг 3 (согласование рода в шаблонах) — регрессии ниже.


class AlwaysRollsRng(NoCritRng):
    """Как NoCritRng, но .random() всегда 0.0 — гарантирует срабатывание любых
    чанс-роллов (контроль landing, отсутствие резиста)."""

    def random(self) -> float:
        return 0.0


class FixedRng(NoCritRng):
    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value


def test_numbness_extends_freeze_past_same_tick_decay() -> None:
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["freeze_duration_bonus"] = 1
    enemy = combatant(2, side=1, kind="mob", will=0)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    # FREEZE — немедленный эффект, декрементится В ТОТ ЖЕ ход (1 без баффа
    # истёк бы сразу); +1 от «Оцепенения» должен пережить этот тик.
    assert enemy.has_effect(EffectKind.FREEZE)


def test_without_numbness_freeze_consumed_same_tick() -> None:
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    enemy = combatant(2, side=1, kind="mob", will=0)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    assert not enemy.has_effect(EffectKind.FREEZE)


def test_deep_freeze_reduces_effective_resist_chance() -> None:
    from game.combat import control, formulas

    target = combatant(2, side=1, will=200)
    base_resist = formulas.control_resist(target.stats.will)
    assert base_resist > 0.15  # иначе тест не показателен

    roll = base_resist - 0.05  # без бонуса резист сработал бы (roll < resist)
    res_without = control.try_apply_control(
        target, base_duration=1, source_id=1, rng=FixedRng(roll), pvp=False
    )
    assert res_without.resisted

    res_with = control.try_apply_control(
        target, base_duration=1, source_id=1, rng=FixedRng(roll), pvp=False, chance_bonus=0.15
    )
    assert res_with.applied


def test_lingering_poison_extends_dot_duration() -> None:
    rng = NoCritRng()
    toxin = combatant(1, side=0, subclass_id="poisoner")
    toxin.buff_modifiers["poison_duration_bonus"] = 1
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(toxin, enemy)

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    dot = enemy.effect_from(EffectKind.DOT, toxin.id)
    assert dot is not None
    assert dot.remaining_ticks == bc.POISONER_POISON_DURATION_TICKS + 1


def test_unyielding_extends_provoke_duration() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers["provoke_duration_bonus"] = 1
    enemy = combatant(2, side=1)
    state = make_session(guardian, enemy)

    resolve_tick(state, {1: skill("guardian_shield_bash", 2)}, rng)
    effect = enemy.effect_from(EffectKind.PROVOKE_PVP, guardian.id)
    assert effect is not None
    assert effect.remaining_ticks == bc.PROVOKE_PVP_DURATION_TICKS + 1


def test_control_landing_message_not_duplicated_same_tick() -> None:
    """Патч 47, баг 2: контроль, наложенный и потреблённый в ОДИН тик, раньше
    печатал и control_line («X скован»), и резолверную «X скован — ход
    потерян» — одно и то же дважды. Должна остаться одна строка."""
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    enemy = combatant(2, side=1, kind="mob", will=0)
    state = make_session(caster, enemy)

    result = resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    lost_turn_lines = [ln for ln in result.lines if "теряет ход" in ln]
    assert len(lost_turn_lines) == 1


def test_lingering_freeze_still_announces_lost_turn_next_tick() -> None:
    """Многоходовая заморозка (лингер С НАЧАЛА хода, без свежего control_line
    в этот тик) обязана по-прежнему показывать «теряет ход» — баг 2 не должен
    заодно убить легитимное сообщение."""
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["freeze_duration_bonus"] = 1
    enemy = combatant(2, side=1, kind="mob", will=0)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    assert enemy.has_effect(EffectKind.FREEZE)
    result2 = resolve_tick(state, {1: attack(2)}, rng)
    assert any("теряет ход" in ln for ln in result2.lines)


def test_control_lines_are_gender_neutral() -> None:
    """Патч 47, баг 3: шаблоны не должны содержать согласуемые по роду
    причастия («скован(а)», «заморожен(а)», «был/была под контролем»)."""
    from game.combat import combat_flavor

    assert "скован" not in combat_flavor.control_line("Тест")
    assert "был" not in combat_flavor.control_blocked_line("Тест")


def test_poison_line_is_gender_neutral() -> None:
    rng = NoCritRng()
    toxin = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(toxin, enemy)
    result = resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    assert any("под действием яда" in ln for ln in result.lines)
    assert not any("отравлен" in ln for ln in result.lines)


# --- Контент: калиброванные значения микробаффов патча 47 ---


def test_calibrated_patch47_buff_values_in_content() -> None:
    buffs = load_content().buffs
    assert buffs["elementalist_numbness"].stat_modifiers["freeze_duration_bonus"] == bc.ELEMENTALIST_NUMBNESS_FREEZE_BONUS_TURNS
    assert buffs["elementalist_deep_freeze"].stat_modifiers["control_chance_bonus"] == bc.ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS
    assert buffs["poisoner_lingering_poison"].stat_modifiers["poison_duration_bonus"] == bc.POISONER_LINGERING_POISON_BONUS_TURNS
    assert buffs["guardian_unyielding"].stat_modifiers["provoke_duration_bonus"] == bc.GUARDIAN_UNYIELDING_PROVOKE_BONUS_TURNS


# --- Патч 47, ч.2: весь оставшийся пул микробаффов Кровавого рыцаря (11 из
# 12 были заглушками — жалоба игрока, что "микробаффы не работают" вообще). ---


def test_thirst_boosts_lifesteal_when_low_hp() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["low_hp_lifesteal_bonus"] = 0.08
    knight.current_hp = round(knight.max_hp * 0.4)  # <50%
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.28)  # 0.20 базовых + 0.08 бафф


def test_thirst_inactive_above_half_hp() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["low_hp_lifesteal_bonus"] = 0.08
    knight.current_hp -= 100  # есть куда лечить, но выше 50%
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.2)  # HP полное — бонус не действует


def test_vein_rupture_boosts_lifesteal_on_crit() -> None:
    rng = FixedRng(0.05)  # target agility=0 -> дожд-чек пропускается; крит гарантирован
    knight = combatant(1, side=0, subclass_id="blood_knight", agility=200)
    knight.buff_modifiers["crit_lifesteal_bonus"] = 0.08
    knight.current_hp -= 100  # есть куда лечить
    enemy = combatant(2, side=1, vitality=500, agility=0)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.28)  # 0.20 базовых + 0.08 крит-бонус


def test_recklessness_boosts_damage() -> None:
    rng = NoCritRng()
    baseline = combatant(1, side=0, subclass_id="blood_knight")
    enemy1 = combatant(2, side=1, vitality=5000)
    resolve_tick(make_session(baseline, enemy1), {1: attack(2)}, rng)
    baseline_damage = enemy1.max_hp - enemy1.current_hp

    boosted = combatant(3, side=0, subclass_id="blood_knight")
    boosted.buff_modifiers["reckless_damage_bonus"] = 0.06
    enemy2 = combatant(4, side=1, vitality=5000)
    resolve_tick(make_session(boosted, enemy2), {3: attack(4)}, rng)
    boosted_damage = enemy2.max_hp - enemy2.current_hp

    assert boosted_damage > baseline_damage


def test_insatiable_adds_unconditional_lifesteal() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["lifesteal_ratio_bonus"] = 0.05
    knight.current_hp -= 100  # есть куда лечить
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.25)  # 0.20 + 0.05 безусловно


def test_eternal_hunger_raises_heal_cap() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight", strength=500)
    knight.buff_modifiers["heal_cap_bonus"] = 0.03
    knight.current_hp = 1  # есть куда лечить без дополнительного капа по остатку HP
    enemy = combatant(2, side=1, vitality=5000)
    state = make_session(knight, enemy)

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    healed = knight.current_hp - 1
    assert healed == round(knight.max_hp * (bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN + 0.03))


def test_second_wind_reduces_incoming_damage_when_low_hp() -> None:
    rng = NoCritRng()
    attacker = combatant(9, side=1)

    victim_no_buff = combatant(1, side=0, vitality=1000)
    victim_no_buff.current_hp = round(victim_no_buff.max_hp * 0.2)
    resolve_tick(make_session(victim_no_buff, attacker), {9: attack(1)}, rng)
    dmg_no_buff = round(victim_no_buff.max_hp * 0.2) - victim_no_buff.current_hp

    attacker2 = combatant(10, side=1)
    victim = combatant(2, side=0, vitality=1000)
    victim.buff_modifiers["low_hp_damage_reduction"] = 0.10
    victim.current_hp = round(victim.max_hp * 0.2)  # <30% порог
    resolve_tick(make_session(victim, attacker2), {10: attack(2)}, rng)
    dmg_with_buff = round(victim.max_hp * 0.2) - victim.current_hp

    assert dmg_with_buff < dmg_no_buff


def test_blood_armor_reduces_incoming_damage_unconditionally() -> None:
    rng = NoCritRng()
    attacker1 = combatant(9, side=1)
    victim_no_buff = combatant(1, side=0, vitality=1000)
    resolve_tick(make_session(victim_no_buff, attacker1), {9: attack(1)}, rng)
    dmg_no_buff = victim_no_buff.max_hp - victim_no_buff.current_hp

    attacker2 = combatant(10, side=1)
    victim = combatant(2, side=0, vitality=1000)
    victim.buff_modifiers["incoming_damage_reduction"] = 0.05
    resolve_tick(make_session(victim, attacker2), {10: attack(2)}, rng)
    dmg_with_buff = victim.max_hp - victim.current_hp

    assert dmg_with_buff < dmg_no_buff


def test_pain_resistant_reduces_crit_damage_taken() -> None:
    rng = FixedRng(0.05)  # attacker agility высокий -> крит гарантирован
    attacker1 = combatant(9, side=1, agility=200)
    victim_no_buff = combatant(1, side=0, vitality=1000, agility=0)
    resolve_tick(make_session(victim_no_buff, attacker1), {9: attack(1)}, rng)
    dmg_no_buff = victim_no_buff.max_hp - victim_no_buff.current_hp

    attacker2 = combatant(10, side=1, agility=200)
    victim = combatant(2, side=0, vitality=1000, agility=0)
    victim.buff_modifiers["crit_damage_taken_reduction"] = 0.15
    resolve_tick(make_session(victim, attacker2), {10: attack(2)}, rng)
    dmg_with_buff = victim.max_hp - victim.current_hp

    assert dmg_with_buff < dmg_no_buff


def test_feast_boosts_crimson_feast_heal_only() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["crimson_feast_heal_bonus"] = 0.10
    enemy = combatant(2, side=1, vitality=5000)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_crimson_feast", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    cost = round(hp_before * bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)
    healed = knight.current_hp - (hp_before - cost)
    assert healed == round(damage_dealt * 0.55)  # 0.45 базовых + 0.10 бафф

    # тот же бафф НЕ действует на Кровопуск (только на Багровый пир)
    knight2 = combatant(3, side=0, subclass_id="blood_knight")
    knight2.buff_modifiers["crimson_feast_heal_bonus"] = 0.10
    knight2.current_hp -= 100  # есть куда лечить
    enemy2 = combatant(4, side=1, vitality=5000)
    state2 = make_session(knight2, enemy2)
    hp_before2 = knight2.current_hp
    resolve_tick(state2, {3: skill("blood_knight_lifesteal_strike", 4)}, rng)
    damage2 = enemy2.max_hp - enemy2.current_hp
    healed2 = knight2.current_hp - hp_before2
    assert healed2 == round(damage2 * 0.2)


def test_shared_thirst_heals_most_injured_ally() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["shared_heal_pct"] = 0.30
    hurt_ally = combatant(3, side=0, vitality=200)
    hurt_ally.current_hp = 1
    healthy_ally = combatant(4, side=0, vitality=200)
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, hurt_ally, healthy_ally, enemy)

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    assert hurt_ally.current_hp > 1
    assert healthy_ally.current_hp == healthy_ally.max_hp  # хил ушёл раненому союзнику


def test_shared_thirst_noop_without_allies() -> None:
    """1×1 бой — союзников нет, дополнительный хил никому не уходит и не падает."""
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["shared_heal_pct"] = 0.30
    knight.current_hp -= 100  # есть куда лечить
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_lifesteal_strike", 2)}, rng)
    damage_dealt = enemy.max_hp - enemy.current_hp
    healed = knight.current_hp - hp_before
    assert healed == round(damage_dealt * 0.2)


def test_blood_pact_reduces_crimson_feast_cost() -> None:
    rng = NoCritRng()
    knight = combatant(1, side=0, subclass_id="blood_knight")
    knight.buff_modifiers["crimson_feast_cost_reduction"] = 0.20
    enemy = combatant(2, side=1, vitality=5000)
    state = make_session(knight, enemy)
    hp_before = knight.current_hp

    resolve_tick(state, {1: skill("blood_knight_crimson_feast", 2)}, rng)
    expected_cost = round(hp_before * bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST * 0.8)
    # без хила проверить сложно (лайфстил тут же восполняет часть) — проверяем
    # напрямую через дефолтный кейс без баффа для сравнения себестоимости
    knight2 = combatant(3, side=0, subclass_id="blood_knight")
    enemy2 = combatant(4, side=1, vitality=5000)
    resolve_tick(make_session(knight2, enemy2), {3: skill("blood_knight_crimson_feast", 4)}, rng)
    default_cost = round(hp_before * bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)
    assert expected_cost < default_cost


def test_shared_feast_boosts_damage() -> None:
    rng = NoCritRng()
    baseline = combatant(1, side=0, subclass_id="blood_knight")
    enemy1 = combatant(2, side=1, vitality=5000)
    resolve_tick(make_session(baseline, enemy1), {1: attack(2)}, rng)
    baseline_damage = enemy1.max_hp - enemy1.current_hp

    boosted = combatant(3, side=0, subclass_id="blood_knight")
    boosted.buff_modifiers["group_damage_bonus"] = 0.05
    enemy2 = combatant(4, side=1, vitality=5000)
    resolve_tick(make_session(boosted, enemy2), {3: attack(4)}, rng)
    boosted_damage = enemy2.max_hp - enemy2.current_hp

    assert boosted_damage > baseline_damage


def test_reckless_and_group_damage_bonus_stack_independently() -> None:
    """Разные ключи (reckless_damage_bonus/group_damage_bonus) — при слиянии
    stat_modifiers пресета (dict.update) не должны перезаписывать друг друга,
    как это было бы с общим damage_bonus."""
    rng = NoCritRng()
    both = combatant(1, side=0, subclass_id="blood_knight")
    both.buff_modifiers["reckless_damage_bonus"] = 0.06
    both.buff_modifiers["group_damage_bonus"] = 0.05
    only_one = combatant(3, side=0, subclass_id="blood_knight")
    only_one.buff_modifiers["reckless_damage_bonus"] = 0.06
    enemy1 = combatant(2, side=1, vitality=5000)
    enemy2 = combatant(4, side=1, vitality=5000)

    resolve_tick(make_session(both, enemy1), {1: attack(2)}, rng)
    resolve_tick(make_session(only_one, enemy2), {3: attack(4)}, rng)
    assert (enemy1.max_hp - enemy1.current_hp) > (enemy2.max_hp - enemy2.current_hp)


def test_calibrated_blood_knight_buff_values_in_content() -> None:
    buffs = load_content().buffs
    assert buffs["blood_knight_thirst"].stat_modifiers["low_hp_lifesteal_bonus"] == bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS
    assert buffs["blood_knight_vein_rupture"].stat_modifiers["crit_lifesteal_bonus"] == bc.BLOOD_KNIGHT_VEIN_RUPTURE_CRIT_LIFESTEAL_BONUS
    assert buffs["blood_knight_recklessness"].stat_modifiers["reckless_damage_bonus"] == bc.BLOOD_KNIGHT_RECKLESSNESS_DAMAGE_BONUS
    assert buffs["blood_knight_insatiable"].stat_modifiers["lifesteal_ratio_bonus"] == bc.BLOOD_KNIGHT_INSATIABLE_LIFESTEAL_BONUS
    assert buffs["blood_knight_eternal_hunger"].stat_modifiers["heal_cap_bonus"] == bc.BLOOD_KNIGHT_ETERNAL_HUNGER_HEAL_CAP_BONUS
    assert buffs["blood_knight_second_wind"].stat_modifiers["low_hp_damage_reduction"] == bc.BLOOD_KNIGHT_SECOND_WIND_DAMAGE_REDUCTION
    assert buffs["blood_knight_blood_armor"].stat_modifiers["incoming_damage_reduction"] == bc.BLOOD_KNIGHT_BLOOD_ARMOR_DAMAGE_REDUCTION
    assert buffs["blood_knight_pain_resistant"].stat_modifiers["crit_damage_taken_reduction"] == bc.BLOOD_KNIGHT_PAIN_RESISTANT_CRIT_REDUCTION
    assert buffs["blood_knight_feast"].stat_modifiers["crimson_feast_heal_bonus"] == bc.BLOOD_KNIGHT_FEAST_CRIMSON_HEAL_BONUS
    assert buffs["blood_knight_shared_thirst"].stat_modifiers["shared_heal_pct"] == bc.BLOOD_KNIGHT_SHARED_THIRST_ALLY_HEAL_PCT
    assert buffs["blood_knight_blood_pact"].stat_modifiers["crimson_feast_cost_reduction"] == bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION
    assert buffs["blood_knight_shared_feast"].stat_modifiers["group_damage_bonus"] == bc.BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS


# --- Патч 49, ч.2: весь оставшийся пул микробаффов Элементалиста (8 из 13
# были заглушками — Пламенная/Ледяная мощь, Мощь бури, Всеобщая стихия,
# Тепловой шок, Цепная молния, Огненный дождь, Ледяное поле). ---


def test_flame_power_boosts_fire_damage() -> None:
    rng = NoCritRng()
    baseline = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    enemy1 = combatant(2, side=1, vitality=5000)
    resolve_tick(make_session(baseline, enemy1), {1: skill("elementalist_fire", 2)}, rng)
    baseline_damage = enemy1.max_hp - enemy1.current_hp

    boosted = combatant(3, side=0, subclass_id="elementalist", intellect=100)
    boosted.buff_modifiers["fire_damage_bonus"] = bc.ELEMENTALIST_FLAME_POWER_BONUS
    enemy2 = combatant(4, side=1, vitality=5000)
    resolve_tick(make_session(boosted, enemy2), {3: skill("elementalist_fire", 4)}, rng)
    boosted_damage = enemy2.max_hp - enemy2.current_hp

    assert boosted_damage > baseline_damage


def test_universal_element_and_specific_bonus_do_not_stack() -> None:
    """Больший из двух модификаторов — не сумма (иначе связка всех четырёх
    даёт +53% сразу, что патч явно запрещает)."""
    rng = NoCritRng()
    specific_only = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    specific_only.buff_modifiers["fire_damage_bonus"] = bc.ELEMENTALIST_FLAME_POWER_BONUS
    enemy1 = combatant(2, side=1, vitality=5000)
    resolve_tick(make_session(specific_only, enemy1), {1: skill("elementalist_fire", 2)}, rng)
    dmg_specific = enemy1.max_hp - enemy1.current_hp

    both = combatant(3, side=0, subclass_id="elementalist", intellect=100)
    both.buff_modifiers["fire_damage_bonus"] = bc.ELEMENTALIST_FLAME_POWER_BONUS
    both.buff_modifiers["all_elements_damage_bonus"] = bc.ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS
    enemy2 = combatant(4, side=1, vitality=5000)
    resolve_tick(make_session(both, enemy2), {3: skill("elementalist_fire", 4)}, rng)
    dmg_both = enemy2.max_hp - enemy2.current_hp

    assert dmg_both == dmg_specific


def test_chain_lightning_extra_target() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["chain_lightning_extra_targets"] = bc.ELEMENTALIST_CHAIN_LIGHTNING_EXTRA_TARGETS
    main = combatant(2, side=1, vitality=5000)
    e3 = combatant(3, side=1, vitality=5000)
    e4 = combatant(4, side=1, vitality=5000)
    e5 = combatant(5, side=1, vitality=5000)
    state = make_session(caster, main, e3, e4, e5)
    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    hit_count = sum(1 for e in (main, e3, e4, e5) if e.current_hp < e.max_hp)
    assert hit_count == 4  # основная + 3 доп. (без баффа было бы 3 = основная + 2)


def test_chain_lightning_default_hits_two_extra_targets() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    main = combatant(2, side=1, vitality=5000)
    e3 = combatant(3, side=1, vitality=5000)
    e4 = combatant(4, side=1, vitality=5000)
    e5 = combatant(5, side=1, vitality=5000)
    state = make_session(caster, main, e3, e4, e5)
    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    hit_count = sum(1 for e in (main, e3, e4, e5) if e.current_hp < e.max_hp)
    assert hit_count == 3


def test_heat_shock_reduces_resist_on_burn_expiry() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["burn_expire_resist_down"] = bc.ELEMENTALIST_HEAT_SHOCK_RESIST_DOWN
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert enemy.effect_from(EffectKind.DOT, caster.id) is not None
    assert not enemy.has_effect(EffectKind.CONTROL_RESIST_DOWN)

    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
    duration = SUBCLASS_SKILL_DEFS["elementalist_fire"].effect_duration
    for _ in range(duration):
        resolve_tick(state, {1: attack(2)}, rng)

    assert enemy.effect_from(EffectKind.DOT, caster.id) is None  # Горение истекло
    assert enemy.has_effect(EffectKind.CONTROL_RESIST_DOWN)


def test_heat_shock_inactive_without_buff() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    enemy = combatant(2, side=1, vitality=5000, level=1)
    state = make_session(caster, enemy)
    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)

    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
    duration = SUBCLASS_SKILL_DEFS["elementalist_fire"].effect_duration
    for _ in range(duration):
        resolve_tick(state, {1: attack(2)}, rng)
    assert not enemy.has_effect(EffectKind.CONTROL_RESIST_DOWN)


def test_firestorm_spreads_burn_to_other_enemies() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["burn_spread_pct"] = bc.ELEMENTALIST_FIRESTORM_SPREAD_PCT
    main = combatant(2, side=1, vitality=5000)
    other = combatant(3, side=1, vitality=5000)
    state = make_session(caster, main, other)
    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)

    main_dot = main.effect_from(EffectKind.DOT, caster.id)
    other_dot = other.effect_from(EffectKind.DOT, caster.id)
    assert main_dot is not None and other_dot is not None
    assert other_dot.value == main_dot.value * bc.ELEMENTALIST_FIRESTORM_SPREAD_PCT


def test_firestorm_inactive_without_buff() -> None:
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    main = combatant(2, side=1, vitality=5000)
    other = combatant(3, side=1, vitality=5000)
    state = make_session(caster, main, other)
    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert other.effect_from(EffectKind.DOT, caster.id) is None


def test_ice_field_chills_other_enemies_on_freeze() -> None:
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    caster.buff_modifiers["ice_field_chill_pct"] = bc.ELEMENTALIST_ICE_FIELD_CHILL_PCT
    main = combatant(2, side=1, kind="mob", will=0)
    other = combatant(3, side=1, kind="mob", will=0)
    state = make_session(caster, main, other)
    result = resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)

    # FREEZE — немедленный эффект, потребляется в тот же ход (см. docstring
    # resolver.py); landing подтверждаем по логу, не по остаточному состоянию.
    assert any("теряет ход" in ln for ln in result.lines)
    assert not main.has_effect(EffectKind.CONTROL_RESIST_DOWN)  # дебафф — соседям, не основной цели
    assert other.has_effect(EffectKind.CONTROL_RESIST_DOWN)


def test_ice_field_inactive_without_buff() -> None:
    rng = AlwaysRollsRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    main = combatant(2, side=1, kind="mob", will=0)
    other = combatant(3, side=1, kind="mob", will=0)
    state = make_session(caster, main, other)
    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    assert not other.has_effect(EffectKind.CONTROL_RESIST_DOWN)


def test_calibrated_elementalist_remaining_buff_values_in_content() -> None:
    buffs = load_content().buffs
    assert buffs["elementalist_flame_power"].stat_modifiers["fire_damage_bonus"] == bc.ELEMENTALIST_FLAME_POWER_BONUS
    assert buffs["elementalist_frost_power"].stat_modifiers["ice_damage_bonus"] == bc.ELEMENTALIST_FROST_POWER_BONUS
    assert buffs["elementalist_storm_power"].stat_modifiers["lightning_damage_bonus"] == bc.ELEMENTALIST_STORM_POWER_BONUS
    assert buffs["elementalist_universal_element"].stat_modifiers["all_elements_damage_bonus"] == bc.ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS
    assert buffs["elementalist_heat_shock"].stat_modifiers["burn_expire_resist_down"] == bc.ELEMENTALIST_HEAT_SHOCK_RESIST_DOWN
    assert buffs["elementalist_chain_lightning"].stat_modifiers["chain_lightning_extra_targets"] == bc.ELEMENTALIST_CHAIN_LIGHTNING_EXTRA_TARGETS
    assert buffs["elementalist_firestorm"].stat_modifiers["burn_spread_pct"] == bc.ELEMENTALIST_FIRESTORM_SPREAD_PCT
    assert buffs["elementalist_ice_field"].stat_modifiers["ice_field_chill_pct"] == bc.ELEMENTALIST_ICE_FIELD_CHILL_PCT
    for buff_id in (
        "elementalist_flame_power", "elementalist_frost_power", "elementalist_storm_power",
        "elementalist_universal_element", "elementalist_heat_shock", "elementalist_chain_lightning",
        "elementalist_firestorm", "elementalist_ice_field",
    ):
        assert buffs[buff_id].implemented is True, buff_id
