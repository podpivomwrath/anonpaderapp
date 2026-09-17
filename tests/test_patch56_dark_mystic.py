"""Патч 56: микробаффы Тёмного мистика.

Единственный хилер игры: пул усиливает конверсию урона в лечение, Оберег и
групповое перераспределение лечения. Групповые баффы обязаны быть нет-опом
в бою один на один - это проверяется отдельно.
"""

from game.combat import balance_config as bc
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


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def mystic(**mods) -> "object":
    c = combatant(1, side=0, subclass_id="dark_mystic")
    c.buff_modifiers = dict(mods)
    return c


def heal_to(result, target_id: int) -> int:
    return sum(h.amount for h in result.heal_renders if h.target_id == target_id)


# --- Конверсия урона в лечение ---


def test_blood_bond_raises_conversion() -> None:
    rng = NoCritRng()

    def healed(mods: dict) -> int:
        healer = mystic(**mods)
        ally = combatant(3, side=0)
        ally.current_hp = ally.max_hp // 2
        enemy = combatant(2, side=1, agility=0, vitality=500)
        result = resolve_tick(make_session(healer, ally, enemy),
                              {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return heal_to(result, ally.id)

    assert healed({"pact_conversion_bonus": bc.DARK_MYSTIC_BLOOD_BOND_BONUS}) > healed({})


def test_dark_resonance_only_for_badly_wounded_target() -> None:
    rng = NoCritRng()

    def healed(ally_hp_pct: float) -> int:
        healer = mystic(resonance_bonus=bc.DARK_MYSTIC_RESONANCE_BONUS)
        ally = combatant(3, side=0)
        ally.current_hp = max(round(ally.max_hp * ally_hp_pct), 1)
        enemy = combatant(2, side=1, agility=0, vitality=500)
        result = resolve_tick(make_session(healer, ally, enemy),
                              {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return heal_to(result, ally.id)

    below = bc.DARK_MYSTIC_RESONANCE_HP_THRESHOLD - 0.1
    above = bc.DARK_MYSTIC_RESONANCE_HP_THRESHOLD + 0.1
    assert healed(below) > healed(above)


# --- Плата собственным здоровьем ---


def test_blood_pact_plus_makes_hp_cost_cheaper() -> None:
    rng = NoCritRng()

    def hp_spent(mods: dict) -> int:
        healer = mystic(**mods)
        ally = combatant(3, side=0)
        before = healer.current_hp
        resolve_tick(make_session(healer, ally), {1: skill("dark_mystic_circle")}, rng)
        # Круг тьмы никого не бьёт - вся разница это заплаченное здоровье
        return before - healer.current_hp

    assert hp_spent({"hp_cost_reduction": bc.DARK_MYSTIC_HP_COST_REDUCTION}) < hp_spent({})


def test_self_denial_costs_hp_and_boosts_pact() -> None:
    rng = NoCritRng()

    def run(mods: dict) -> tuple[int, int]:
        healer = mystic(**mods)
        enemy = combatant(2, side=1, agility=0, vitality=500)
        hp_before = enemy.current_hp
        resolve_tick(make_session(healer, enemy), {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return hp_before - enemy.current_hp, healer.current_hp

    plain_damage, plain_hp = run({})
    denial_damage, denial_hp = run({"self_denial": 1.0})
    assert denial_damage > plain_damage
    assert denial_hp < plain_hp  # заплатил собственным здоровьем


def test_dark_reward_charges_after_hp_spending_skill() -> None:
    rng = NoCritRng()
    healer = mystic(dark_reward_bonus=bc.DARK_MYSTIC_DARK_REWARD_BONUS)
    ally = combatant(3, side=0)
    resolve_tick(make_session(healer, ally), {1: skill("dark_mystic_circle")}, rng)
    assert healer.dark_reward_ready is True


def test_dark_reward_is_spent_by_next_pact() -> None:
    rng = NoCritRng()

    def damage(ready: bool) -> int:
        healer = mystic(dark_reward_bonus=bc.DARK_MYSTIC_DARK_REWARD_BONUS)
        healer.dark_reward_ready = ready
        enemy = combatant(2, side=1, agility=0, vitality=500)
        before = enemy.current_hp
        resolve_tick(make_session(healer, enemy), {1: skill("dark_mystic_blood_pact", 2)}, rng)
        assert healer.dark_reward_ready is False  # заряд израсходован в любом случае
        return before - enemy.current_hp

    assert damage(True) > damage(False)


def test_edge_works_only_below_threshold() -> None:
    rng = NoCritRng()

    def damage(hp_pct: float) -> int:
        healer = mystic(edge_bonus=bc.DARK_MYSTIC_EDGE_BONUS)
        healer.current_hp = max(round(healer.max_hp * hp_pct), 1)
        enemy = combatant(2, side=1, agility=0, vitality=500)
        before = enemy.current_hp
        resolve_tick(make_session(healer, enemy), {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return before - enemy.current_hp

    assert damage(bc.DARK_MYSTIC_EDGE_HP_THRESHOLD - 0.1) > damage(1.0)


# --- Оберег ---


def test_blood_ward_and_steadfast_ward_raise_absorption() -> None:
    rng = NoCritRng()

    def absorb(mods: dict) -> float:
        healer = mystic(**mods)
        resolve_tick(make_session(healer, combatant(2, side=1)), {1: skill("dark_mystic_ward")}, rng)
        return healer.effect_total(EffectKind.SHIELD_POOL)

    plain = absorb({})
    assert absorb({"ward_shield_bonus": bc.DARK_MYSTIC_WARD_SHIELD_BONUS}) > plain
    assert absorb({"ward_absorb_bonus": bc.DARK_MYSTIC_STEADFAST_WARD_BONUS}) > plain


def test_steadfast_ward_costs_extra_cooldown() -> None:
    rng = NoCritRng()
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    base_cd = SUBCLASS_SKILL_DEFS["dark_mystic_ward"].cd
    healer = mystic(ward_absorb_bonus=bc.DARK_MYSTIC_STEADFAST_WARD_BONUS)
    resolve_tick(make_session(healer, combatant(2, side=1)), {1: skill("dark_mystic_ward")}, rng)
    # резолвер уже стикнул кулдауны в конце хода, поэтому сравниваем со сдвигом
    assert healer.cooldowns["dark_mystic_ward"] == base_cd + bc.DARK_MYSTIC_STEADFAST_WARD_CD - 1


def test_ward_passed_on_covers_second_ally_only_in_group() -> None:
    rng = NoCritRng()
    healer = mystic(ward_transfer=1.0)
    hurt = combatant(3, side=0)
    hurt.current_hp = hurt.max_hp // 4
    second = combatant(4, side=0)
    second.current_hp = second.max_hp // 2
    resolve_tick(make_session(healer, hurt, second, combatant(2, side=1)),
                 {1: skill("dark_mystic_ward")}, rng)
    assert hurt.effect_total(EffectKind.SHIELD_POOL) > 0
    assert second.effect_total(EffectKind.SHIELD_POOL) > 0

    # В бою один на один передавать оберег некому - лишних эффектов не появляется
    solo = mystic(ward_transfer=1.0)
    enemy = combatant(2, side=1)
    resolve_tick(make_session(solo, enemy), {1: skill("dark_mystic_ward")}, rng)
    assert enemy.effect_total(EffectKind.SHIELD_POOL) == 0


# --- Групповое перераспределение ---


def test_shared_pact_reaches_second_wounded_ally() -> None:
    rng = NoCritRng()
    healer = mystic(shared_pact_pct=bc.DARK_MYSTIC_SHARED_PACT_PCT)
    worst = combatant(3, side=0)
    worst.current_hp = worst.max_hp // 4
    second = combatant(4, side=0)
    second.current_hp = second.max_hp // 2
    enemy = combatant(2, side=1, agility=0, vitality=500)

    result = resolve_tick(make_session(healer, worst, second, enemy),
                          {1: skill("dark_mystic_blood_pact", 2)}, rng)
    assert heal_to(result, second.id) > 0
    assert heal_to(result, second.id) < heal_to(result, worst.id)


def test_shared_pact_is_noop_in_duel() -> None:
    rng = NoCritRng()
    healer = mystic(shared_pact_pct=bc.DARK_MYSTIC_SHARED_PACT_PCT)
    enemy = combatant(2, side=1, agility=0, vitality=500)
    result = resolve_tick(make_session(healer, enemy),
                          {1: skill("dark_mystic_blood_pact", 2)}, rng)
    assert heal_to(result, enemy.id) == 0


def test_circle_of_darkness_adds_group_heal_on_schedule() -> None:
    rng = NoCritRng()

    def group_heal(tick: int) -> int:
        healer = mystic(circle_interval=float(bc.DARK_MYSTIC_CIRCLE_INTERVAL),
                        circle_pct=bc.DARK_MYSTIC_CIRCLE_PCT)
        ally = combatant(3, side=0)
        ally.current_hp = ally.max_hp // 2
        enemy = combatant(2, side=1, agility=0, vitality=500)
        state = make_session(healer, ally, enemy)
        state.tick_number = tick
        result = resolve_tick(state, {1: skill("dark_mystic_blood_pact", 2)}, rng)
        return heal_to(result, ally.id)

    on_schedule = group_heal(bc.DARK_MYSTIC_CIRCLE_INTERVAL)
    off_schedule = group_heal(bc.DARK_MYSTIC_CIRCLE_INTERVAL + 1)
    assert on_schedule > off_schedule


def test_echo_turns_overheal_into_ally_shield() -> None:
    rng = NoCritRng()
    healer = mystic(heal_overflow_shield=bc.DARK_MYSTIC_ECHO_PCT)
    # Пакт лечит САМОГО раненого союзника, поэтому перелечиться должен именно
    # он: держим его чуть ниже полного, а соседа - полностью здоровым.
    topped_up = combatant(3, side=0)
    topped_up.current_hp = topped_up.max_hp - 1
    neighbour = combatant(4, side=0)
    enemy = combatant(2, side=1, agility=0, vitality=500)

    resolve_tick(make_session(healer, topped_up, neighbour, enemy),
                 {1: skill("dark_mystic_blood_pact", 2)}, rng)
    assert neighbour.effect_total(EffectKind.SHIELD_POOL) > 0


def test_echo_is_noop_without_allies() -> None:
    rng = NoCritRng()
    healer = mystic(heal_overflow_shield=bc.DARK_MYSTIC_ECHO_PCT)
    enemy = combatant(2, side=1, agility=0, vitality=500)
    resolve_tick(make_session(healer, enemy), {1: skill("dark_mystic_blood_pact", 2)}, rng)
    assert enemy.effect_total(EffectKind.SHIELD_POOL) == 0
