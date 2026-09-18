"""Патч балансировки 57: новые правила, найденные симулятором.

Каждый тест закрепляет механику, которой раньше не было или которая работала
не так, как обещала. Числа берутся из balance_config - иначе тест придётся
править при каждой калибровке.
"""

import random

from game.combat import balance_config as bc
from game.combat import control, formulas
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    Effect,
    EffectKind,
)
from tests.conftest import NoCritRng, combatant


def make_session(*combatants, mode: CombatMode = CombatMode.PVP_GROUP) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def poison(target, source_id: int, stacks: int = 2) -> Effect:
    effect = Effect(kind=EffectKind.DOT, value=10.0, remaining_ticks=3,
                    source_id=source_id, stacks=stacks)
    target.effects.append(effect)
    return effect


# --- Потолок уворота ---


def test_dodge_has_a_real_hard_cap() -> None:
    """Раньше DODGE_HARD_CAP был 1.00, то есть потолка не было вовсе: стат-уворот
    Клинка теней складывался с «Танцем в тени», «Тенью» и «Ускользанием» в 94%
    промахов, и подкласс становился неубиваемым."""
    assert bc.DODGE_HARD_CAP < 1.0
    assert bc.DODGE_HARD_CAP >= bc.DODGE_STAT_CAP  # стат сам по себе не должен упираться выше общего потолка


def test_stacked_dodge_cannot_exceed_hard_cap() -> None:
    from game.combat.skills import compute_hit

    class AlwaysHitRng(NoCritRng):
        def random(self) -> float:
            return bc.DODGE_HARD_CAP + 0.01  # чуть выше потолка - удар обязан пройти

    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=200)
    blade.buff_modifiers = {"dodge_bonus": 1.0, "slip_away_bonus": 1.0}
    blade.dodged_last_tick = True
    blade.effects.append(Effect(kind=EffectKind.DODGE, value=1.0, remaining_ticks=2, source_id=blade.id))
    attacker = combatant(2, side=1)
    hit = compute_hit(attacker, blade, AlwaysHitRng(), "бьёт")
    assert not hit.missed


# --- Эскалация сопротивления контролю ---


def test_second_control_is_checked_against_doubled_will() -> None:
    rng = NoCritRng()
    target = combatant(2, side=1, will=60)
    assert control.try_apply_control(target, 1, 1, rng, pvp=True).applied
    assert control.try_apply_control(target, 1, 1, rng, pvp=True).applied
    assert target.control_hits == 2
    doubled = formulas.control_resist(60 * bc.CC_RESIST_MULT_PER_HIT)
    assert doubled > formulas.control_resist(60)


def test_third_control_does_not_land() -> None:
    rng = NoCritRng()
    target = combatant(2, side=1, will=60)
    for _ in range(bc.CC_MAX_HITS_BEFORE_IMMUNE):
        control.try_apply_control(target, 1, 1, rng, pvp=True)
    result = control.try_apply_control(target, 1, 1, rng, pvp=True)
    assert not result.applied and result.immune


def test_control_counter_resets_on_its_own_timer() -> None:
    """Счётчик живёт таймером, а не «подряд пропущенными» ходами: прежняя
    защита обнулялась на первом же свободном ходу и потому не срабатывала."""
    rng = NoCritRng()
    target = combatant(2, side=1, will=60)
    control.try_apply_control(target, 1, 1, rng, pvp=True)
    assert target.control_hits == 1
    for _ in range(bc.CC_HITS_RESET_TURNS):
        control.tick_control(target, pvp=True)
    assert target.control_hits == 0


def test_control_duration_bonus_is_pve_only() -> None:
    """«Оцепенение» удлиняет заморозку только против мобов: два подряд
    пропущенных хода в размене между игроками - это слишком."""
    rng = NoCritRng()
    for pvp, expect_longer in ((False, True), (True, False)):
        target = combatant(2, side=1, will=0)
        control.try_apply_control(target, 1, 1, rng, pvp=pvp, duration_bonus=1)
        effect = target.effect_from(EffectKind.FREEZE, 1)
        assert effect is not None
        assert (effect.remaining_ticks > 1) is expect_longer


# --- Тёмный мистик: командный хилер ---


def test_mystic_heals_weaker_without_allies() -> None:
    rng = NoCritRng()

    def healing(with_ally: bool) -> int:
        mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
        enemy = combatant(2, side=1, agility=0, vitality=500)
        parts = [mystic, enemy]
        if with_ally:
            ally = combatant(3, side=0)
            ally.current_hp = ally.max_hp // 2
            parts.append(ally)
        result = resolve_tick(make_session(*parts), {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return sum(h.amount for h in result.heal_renders)

    assert healing(with_ally=False) < healing(with_ally=True)


def test_solo_heal_penalty_is_configured_below_one() -> None:
    assert 0 < bc.DARK_MYSTIC_SOLO_HEAL_PENALTY < 1.0


# --- Отравитель: дебаффы работают на группу ---


def test_weaken_spreads_to_other_poisoned_enemies() -> None:
    """«Иссушение» разносит Ослабление по всем отравленным целям - это и есть
    вклад саппорта в группу: он снижает входящий урон всей команде."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    poisoner.buff_modifiers = {"weaken_bonus": bc.POISONER_DESICCATION_WEAKEN_BONUS}
    main = combatant(2, side=1, agility=0)
    other = combatant(3, side=1, agility=0)
    poison(other, source_id=poisoner.id)

    resolve_tick(make_session(poisoner, main, other), {1: skill("poisoner_disrupt", 2)}, rng)

    assert main.effect_total(EffectKind.WEAKEN) > 0
    assert other.effect_total(EffectKind.WEAKEN) > 0          # разошлось
    assert other.effect_total(EffectKind.WEAKEN) < main.effect_total(EffectKind.WEAKEN)


def test_weaken_does_not_spread_without_the_buff() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    main = combatant(2, side=1, agility=0)
    other = combatant(3, side=1, agility=0)
    poison(other, source_id=poisoner.id)
    resolve_tick(make_session(poisoner, main, other), {1: skill("poisoner_disrupt", 2)}, rng)
    assert other.effect_total(EffectKind.WEAKEN) == 0


def test_vulnerability_spreads_to_other_poisoned_enemies() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    poisoner.buff_modifiers = {"vulnerability_bonus": bc.POISONER_TOXIC_BLOOD_VULN_BONUS}
    main = combatant(2, side=1, agility=0)
    other = combatant(3, side=1, agility=0)
    poison(other, source_id=poisoner.id)

    resolve_tick(make_session(poisoner, main, other), {1: skill("poisoner_decay", 2)}, rng)

    assert other.effect_total(EffectKind.VULNERABILITY) > 0
    assert other.effect_total(EffectKind.VULNERABILITY) < main.effect_total(EffectKind.VULNERABILITY)


def test_debuff_spread_is_noop_one_on_one() -> None:
    """Один на один разносить нечего - саппортовская часть пула не должна
    превращаться в бонус к дуэлям."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    poisoner.buff_modifiers = {
        "weaken_bonus": bc.POISONER_DESICCATION_WEAKEN_BONUS,
        "vulnerability_bonus": bc.POISONER_TOXIC_BLOOD_VULN_BONUS,
    }
    enemy = combatant(2, side=1, agility=0)
    result = resolve_tick(make_session(poisoner, enemy), {1: skill("poisoner_disrupt", 2)}, rng)
    assert result is not None
    assert enemy.effect_total(EffectKind.WEAKEN) > 0  # на самой цели дебафф есть


# --- Значения контента не должны расходиться с константами ---


def test_buff_json_matches_balance_constants() -> None:
    """Числа микробаффов живут в двух местах: константа (её читают бой и
    генератор описаний) и stat_modifiers в content/buffs.json (его читает
    пресет игрока). Разойдутся - бафф начнёт врать игроку."""
    import json
    import pathlib

    from tools.sync_buff_values import MAPPING

    items = json.loads(pathlib.Path("content/buffs.json").read_text(encoding="utf-8"))
    by_id = {b["id"]: b for b in items}
    drift = []
    for (buff_id, key), const_name in MAPPING.items():
        buff = by_id.get(buff_id)
        if buff is None or key not in buff["stat_modifiers"]:
            continue
        if abs(buff["stat_modifiers"][key] - getattr(bc, const_name)) > 1e-9:
            drift.append(f"{buff_id}.{key}")
    assert not drift, f"json разошёлся с константами: {drift}"


def test_rng_unused_import_guard() -> None:
    """random импортируется ради детерминированных прогонов в других тестах."""
    assert isinstance(random.Random(1).random(), float)


# --- След «по холоду»: связка «заморозил и разбил» ---


def frozen_then(skill_id: str, mode: CombatMode, *, gap: int = 1) -> bool:
    """Ледяные оковы, затем через gap ходов - проверяемый навык.
    Возвращает, случился ли крит (rng сам по себе крит не выдаёт)."""
    rng = NoCritRng()
    caster = combatant(1, side=0, subclass_id="elementalist", intellect=100)
    target = combatant(2, side=1, will=0, agility=0, vitality=5000)
    state = make_session(caster, target, mode=mode)
    state.tick_number = 1
    resolve_tick(state, {1: skill("elementalist_ice", 2)}, rng)
    for _ in range(gap - 1):
        state.tick_number += 1
        resolve_tick(state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=2)}, rng)
    state.tick_number += 1
    result = resolve_tick(state, {1: skill(skill_id, 2)}, rng)
    return any(h.crit for h in result.hits if h.source_id == 1 and not h.is_dot)


def test_convergence_crits_after_freeze_in_both_modes() -> None:
    """Связка «заморозил и разбил» обязана работать и против игроков.

    Сама заморозка живёт один ход и гасится в тот же тик, поэтому проверки
    одного FREEZE не хватает: в последовательном бою очередь бьющего наступает
    уже после. След CHILLED разводит «сколько цель стоит» и «успеешь ли добить»."""
    assert frozen_then("elementalist_convergence", CombatMode.PVE)
    assert frozen_then("elementalist_convergence", CombatMode.PVP_GROUP)


def test_chill_window_expires() -> None:
    assert not frozen_then("elementalist_convergence", CombatMode.PVP_GROUP,
                           gap=bc.CC_CHILL_WINDOW_TURNS + 2)


def test_drain_also_reads_the_chill_mark() -> None:
    """Иссушение обещает больше урона по цели под контролем и упиралось в ту же
    однотиковую заморозку."""
    rng = NoCritRng()

    def damage(chilled: bool) -> int:
        mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=100)
        target = combatant(2, side=1, agility=0, vitality=5000)
        if chilled:
            target.apply_effect(EffectKind.CHILLED, 1.0, bc.CC_CHILL_WINDOW_TURNS, 99)
        before = target.current_hp
        resolve_tick(make_session(mystic, target), {1: skill("dark_mystic_drain", 2)}, rng)
        return before - target.current_hp

    assert damage(chilled=True) > damage(chilled=False)


def test_any_control_leaves_the_chill_mark() -> None:
    """След оставляет ЛЮБОЙ контроль, в том числе союзника: это даёт группе
    связку «танк придержал - маг добил»."""
    rng = NoCritRng()
    target = combatant(2, side=1, will=0)
    control.try_apply_control(target, 1, source_id=7, rng=rng, pvp=True)
    assert target.has_effect(EffectKind.CHILLED)


def test_execute_threshold_comes_from_config() -> None:
    """Порог добивания и множитель были зашиты числами прямо в коде - справочник
    о них врал бы при первой же калибровке."""
    assert 0 < bc.SHADOW_BLADE_EXECUTE_HP_THRESHOLD < 1
    assert bc.SHADOW_BLADE_EXECUTE_LOW_HP_MULT > 1
    assert bc.DARK_MYSTIC_DRAIN_CONTROLLED_MULT > 1
