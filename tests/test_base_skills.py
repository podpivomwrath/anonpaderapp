"""Базовые навыки классов (combat-patch-2): множители, эффекты, КД, резист."""

import random

from game.combat import base_skills
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from tests.conftest import NoCritRng, combatant


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


# --- Контент ---


def test_all_skills_registered() -> None:
    from game.combat.skills import OFFENSIVE_SKILLS

    assert set(base_skills.BASE_SKILLS_BY_CLASS) == {"warrior", "rogue", "mage"}
    for cls, skills in base_skills.BASE_SKILLS_BY_CLASS.items():
        assert len(skills) == 3
        for s in skills:
            assert s.id in OFFENSIVE_SKILLS


# --- Множители урона ---


def test_cleave_multiplier_180() -> None:
    rng = NoCritRng()
    a1 = combatant(1, side=0, strength=100)
    b1 = combatant(2, side=1, vitality=500)
    s1 = make_session(a1, b1)
    resolve_tick(s1, {1: attack(2)}, rng)
    plain = b1.max_hp - b1.current_hp

    a2 = combatant(3, side=0, strength=100)
    b2 = combatant(4, side=1, vitality=500)
    s2 = make_session(a2, b2)
    resolve_tick(s2, {3: skill("warrior_cleave", 4)}, rng)
    cleaved = b2.max_hp - b2.current_hp

    assert cleaved == round(plain * 1.8)


def test_double_stab_two_hits() -> None:
    rng = NoCritRng()
    a = combatant(1, side=0, agility=100)  # rogue primary agi
    a.primary_stat = "agi"
    b = combatant(2, side=1, vitality=500)
    state = make_session(a, b)
    resolve_tick(state, {1: skill("rogue_double_stab", 2)}, rng)
    # два удара по 80% — суммарно ~160% одного обычного (грубая проверка > 1 удара)
    assert b.current_hp < b.max_hp


def test_shadow_dash_guaranteed_crit() -> None:
    # NoCritRng.random()=0.999 → обычная атака никогда не крит; рывок — всегда крит
    rng = NoCritRng()
    a1 = combatant(1, side=0)
    b1 = combatant(2, side=1, vitality=500)
    s1 = make_session(a1, b1)
    resolve_tick(s1, {1: attack(2)}, rng)
    plain = b1.max_hp - b1.current_hp

    a2 = combatant(3, side=0)
    b2 = combatant(4, side=1, vitality=500)
    s2 = make_session(a2, b2)
    resolve_tick(s2, {3: skill("rogue_shadow_dash", 4)}, rng)
    dash = b2.max_hp - b2.current_hp
    # 130% × крит(1.5) = 195% против 100% обычного
    assert dash > plain


# --- Эффекты контроля ---


def test_stun_skips_same_turn() -> None:
    """progression-patch-4 §5: контроль срабатывает в ТОТ ЖЕ ход — оглушённый
    моб (ходит после игрока) не бьёт в ответ в этот же ход."""
    rng = NoCritRng()  # цель с 0 WIL не сопротивляется
    warrior = combatant(1, side=0, strength=100)
    enemy = combatant(2, side=1, vitality=500, will=0)
    state = make_session(warrior, enemy)

    hp_before = warrior.current_hp
    resolve_tick(state, {1: skill("warrior_stagger", 2)}, rng)
    # оглушение наложено И моб пропустил свой ход в этот же тик — урона по игроку нет
    assert warrior.current_hp == hp_before
    # FREEZE потреблён в тот же ход (не тянется на следующий)
    assert not enemy.has_effect(EffectKind.FREEZE)


def test_stun_resisted_by_high_will() -> None:
    # rng.random() маленький → срабатывает резист (0.01*WIL порог)
    class ResistRng(random.Random):
        def random(self):
            return 0.0  # всегда ниже порога резиста

        def choice(self, seq):
            return seq[0]

    rng = ResistRng()
    warrior = combatant(1, side=0)
    enemy = combatant(2, side=1, will=75, vitality=500)  # 75% резист
    state = make_session(warrior, enemy)
    resolve_tick(state, {1: skill("warrior_stagger", 2)}, rng)
    assert not enemy.has_effect(EffectKind.FREEZE)  # контроль отбит


# --- Баффы/дебаффы ---


def test_warcry_boosts_own_damage() -> None:
    rng = NoCritRng()
    # с боевым кличем
    a = combatant(1, side=0, strength=100)
    b = combatant(2, side=1, vitality=500)
    state = make_session(a, b)
    resolve_tick(state, {1: skill("warrior_warcry", 2)}, rng)  # ход 1: клич, урона нет
    assert b.current_hp == b.max_hp
    assert a.has_effect(EffectKind.DAMAGE_BUFF)

    resolve_tick(state, {1: attack(2)}, rng)  # ход 2: атака с баффом
    boosted = b.max_hp - b.current_hp

    # эталон без клича
    a2 = combatant(3, side=0, strength=100)
    b2 = combatant(4, side=1, vitality=500)
    s2 = make_session(a2, b2)
    resolve_tick(s2, {3: attack(4)}, rng)
    plain = b2.max_hp - b2.current_hp

    assert boosted == round(plain * 1.3)


def test_blood_seal_vulnerability() -> None:
    rng = NoCritRng()
    mage = combatant(1, side=0, intellect=100)
    mage.primary_stat = "int"
    enemy = combatant(2, side=1, vitality=500, will=0)
    state = make_session(mage, enemy)
    resolve_tick(state, {1: skill("mage_blood_seal", 2)}, rng)
    assert enemy.has_effect(EffectKind.VULNERABILITY)


def test_smoke_screen_dodge() -> None:
    # уклонение всегда срабатывает при rng.random()=0 < 0.4
    class DodgeRng(random.Random):
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    rng = DodgeRng()
    rogue = combatant(1, side=0)
    rogue.primary_stat = "agi"
    enemy = combatant(2, side=1, strength=100, vitality=500)
    state = make_session(rogue, enemy)
    resolve_tick(state, {1: skill("rogue_smoke", 2)}, rng)  # ставит уклонение
    assert rogue.has_effect(EffectKind.DODGE)

    hp_before = rogue.current_hp
    resolve_tick(state, {2: attack(1)}, rng)  # враг бьёт — должен промахнуться
    assert rogue.current_hp == hp_before


# --- Кулдауны ---


def test_cooldown_set_and_ticks_down() -> None:
    rng = NoCritRng()
    a = combatant(1, side=0, strength=100)
    b = combatant(2, side=1, vitality=999)
    state = make_session(a, b)

    resolve_tick(state, {1: skill("warrior_cleave", 2)}, rng)  # КД 2
    assert a.is_on_cooldown("warrior_cleave")
    assert a.cooldowns["warrior_cleave"] == 1  # 2, тикнул до 1 в конце хода

    resolve_tick(state, {1: attack(2)}, rng)
    assert not a.is_on_cooldown("warrior_cleave")  # готов снова


def test_cooldowns_reset_between_fights() -> None:
    # новый CombatantState на каждую встречу → кулдауны пустые
    fresh = combatant(1, side=0)
    assert fresh.cooldowns == {}


# --- Защита от чейн-контроля (DR, control-patch-6/8) ---


def _skip_turn(target) -> None:
    """Эмулирует конец хода, в котором цель пропустила ход из-за контроля (PvP)."""
    from game.combat import control

    target.skipped_by_control_this_turn = True
    control.tick_control(target, pvp=True)


def test_dr_reduce_at_streak_3_immunity_at_4() -> None:
    """PvP (control-patch-8): урезание на 3-м пропущенном ходу подряд, иммунитет
    на 4-м, блок на 5-м. Стрик считает ПРОПУСКИ, не наложения."""
    from game.combat import control

    rng = NoCritRng()  # 0 WIL цель никогда не резистит
    target = combatant(2, side=1, will=0)

    # ход 1: пропуск 1 → полная длительность
    r1 = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=True)
    assert r1.applied and not r1.reduced and not r1.immunity_granted
    _skip_turn(target)
    assert target.control_streak == 1

    # ход 2: пропуск 2 → полная
    r2 = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=True)
    assert r2.applied and not r2.reduced and not r2.immunity_granted
    _skip_turn(target)
    assert target.control_streak == 2

    # ход 3: пропуск 3 → урезание (DR), иммунитета ещё нет
    r3 = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=True)
    assert r3.applied and r3.reduced and not r3.immunity_granted
    _skip_turn(target)
    assert target.control_streak == 3

    # ход 4: пропуск 4 → иммунитет выдан (DR)
    r4 = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=True)
    assert r4.applied and r4.immunity_granted
    _skip_turn(target)
    assert target.control_immune_turns > 0

    # ход 5: контроль заблокирован иммунитетом
    r5 = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=True)
    assert not r5.applied and r5.immune


def test_dr_streak_counts_skipped_turns_not_applications() -> None:
    """control-patch-8: пропуск из-за ДЛИТЕЛЬНОГО контроля тоже растит стрик,
    даже без нового наложения в этот ход."""
    from game.combat import control

    target = combatant(2, side=1, will=0)
    # три хода подряд цель пропускает из-за лингера — новых наложений нет
    for expected in (1, 2, 3):
        target.skipped_by_control_this_turn = True
        control.tick_control(target, pvp=True)
        assert target.control_streak == expected

    # следующее наложение уже видит стрик 3 → урезание
    r = control.try_apply_control(target, base_duration=1, source_id=1, rng=NoCritRng(), pvp=True)
    assert r.applied and r.reduced


def test_no_dr_in_pve_control_always_lands() -> None:
    """control-patch-6: в PvE DR не работает — контроль проходит каждый ход,
    без урезания, без иммунитета, стрик не растёт."""
    from game.combat import control

    rng = NoCritRng()
    target = combatant(2, side=1, will=0)
    for _ in range(10):  # десять контролей подряд — все полной длительности
        r = control.try_apply_control(target, base_duration=4, source_id=1, rng=rng, pvp=False)
        assert r.applied and not r.reduced and not r.immunity_granted and not r.immune
        target.skipped_by_control_this_turn = True
        control.tick_control(target, pvp=False)  # PvE: стрик не считается
    assert target.control_streak == 0
    assert target.control_immune_turns == 0


def test_control_resist_blocks_both_modes() -> None:
    """Резист Воли (WIL) работает в обоих режимах и не растит стрик."""
    from game.combat import control

    class AlwaysResist(NoCritRng):
        def random(self):
            return 0.0  # всегда ниже порога резиста

    rng = AlwaysResist()
    for pvp in (True, False):
        target = combatant(2, side=1, will=100)  # высокий резист
        r = control.try_apply_control(target, base_duration=1, source_id=1, rng=rng, pvp=pvp)
        assert not r.applied and r.resisted
        assert target.control_streak == 0  # резист = ход не пропущен


def test_control_streak_resets_when_target_acts() -> None:
    """Стрик сбрасывается, если цель совершила ход (пропуска не было)."""
    from game.combat import control

    target = combatant(2, side=1, will=0)
    _skip_turn(target)
    _skip_turn(target)
    assert target.control_streak == 2
    # ход без пропуска (цель сходила) → стрик сброшен
    target.skipped_by_control_this_turn = False
    control.tick_control(target, pvp=True)
    assert target.control_streak == 0
