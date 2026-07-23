"""Одновременный резолв тика: фазы, таунт, щиты, заморозка, ничья."""

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


def make_session(mode: CombatMode, *combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode)
    for c in combatants:
        state.add(c)
    return state


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def test_simultaneous_damage() -> None:
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    state = make_session(CombatMode.PVP_GROUP, a, b)
    result = resolve_tick(state, {1: attack(2), 2: attack(1)}, NoCritRng())
    assert a.current_hp < a.max_hp
    assert b.current_hp < b.max_hp
    assert not result.finished


def test_draw_on_mutual_death() -> None:
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    a.current_hp = 1
    b.current_hp = 1
    state = make_session(CombatMode.PVP_GROUP, a, b)
    result = resolve_tick(state, {1: attack(2), 2: attack(1)}, NoCritRng())
    assert result.finished and result.draw
    assert sorted(result.deaths) == [1, 2]


def test_winner_side() -> None:
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    b.current_hp = 1
    state = make_session(CombatMode.PVP_GROUP, a, b)
    result = resolve_tick(state, {1: attack(2), 2: DeclaredAction(type=ActionType.SKIP)}, NoCritRng())
    assert result.finished and not result.draw
    assert result.winner_side == 0


def test_guardian_block_reduces_incoming() -> None:
    """Блок — реактивная защита в этот же тик."""
    rng = NoCritRng()
    # без блока
    a1 = combatant(1, side=0, subclass_id="guardian")
    b1 = combatant(2, side=1)
    state1 = make_session(CombatMode.PVP_GROUP, a1, b1)
    resolve_tick(state1, {2: attack(1)}, rng)
    plain_damage = a1.max_hp - a1.current_hp

    # с блоком
    a2 = combatant(1, side=0, subclass_id="guardian")
    b2 = combatant(2, side=1)
    state2 = make_session(CombatMode.PVP_GROUP, a2, b2)
    resolve_tick(state2, {1: skill("guardian_block"), 2: attack(1)}, rng)
    blocked_damage = a2.max_hp - a2.current_hp

    assert blocked_damage == round(plain_damage * 0.5) or blocked_damage < plain_damage


def test_guardian_group_shield_protects_same_tick() -> None:
    """Щит, поставленный этим же действием, поглощает урон этого тика."""
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian", vitality=100)
    ally = combatant(2, side=0)
    ally.current_hp = ally.max_hp // 2  # наименьший % HP — цель щита
    enemy = combatant(3, side=1)
    state = make_session(CombatMode.PVP_GROUP, guardian, ally, enemy)

    hp_before = ally.current_hp
    result = resolve_tick(
        state, {1: skill("guardian_group_shield"), 3: attack(2)}, rng
    )
    absorbed_line = [l for l in result.lines if "поглощает" in l]
    assert absorbed_line, result.lines
    # урон по союзнику полностью съеден щитом (100 VIT * 1.0 >= урон врага)
    assert ally.current_hp == hp_before


def test_taunt_forces_mob_target_in_pve() -> None:
    """PvE: мобы ходят после игроков — таунт форсит их цель в этот же тик."""
    rng = NoCritRng()  # choice → первый в списке (союзник, не страж)
    ally = combatant(1, side=0)          # первым в choice был бы он
    guardian = combatant(2, side=0, subclass_id="guardian")
    wolf = combatant(3, side=1, kind="mob", name="Волк")
    state = make_session(CombatMode.PVE, ally, guardian, wolf)

    resolve_tick(state, {2: skill("guardian_provoke")}, rng)
    assert ally.current_hp == ally.max_hp          # союзника не тронули
    assert guardian.current_hp < guardian.max_hp   # волк форсирован на стража


def test_provoke_in_pvp_is_debuff_not_force() -> None:
    """PvP-провокация не форсит цель, а снижает урон врага по другим целям.

    Обе стороны действуют вслепую в одно окно: провокация (фаза защиты)
    применяется раньше вражеской атаки (фаза урона) того же тика.
    """
    rng = NoCritRng()

    # эталон: враг бьёт союзника без провокации
    base_ally = combatant(11, side=0)
    base_enemy = combatant(12, side=1)
    baseline_state = make_session(CombatMode.PVP_GROUP, base_ally, base_enemy)
    resolve_tick(baseline_state, {12: attack(11)}, rng)
    baseline = base_ally.max_hp - base_ally.current_hp

    # тот же тик: страж провоцирует, враг бьёт союзника (не провоцировавшего)
    guardian = combatant(1, side=0, subclass_id="guardian")
    ally = combatant(2, side=0)
    enemy = combatant(3, side=1)
    state = make_session(CombatMode.PVP_GROUP, guardian, ally, enemy)
    resolve_tick(state, {1: skill("guardian_provoke"), 3: attack(2)}, rng)
    reduced = ally.max_hp - ally.current_hp

    assert reduced < baseline
    # а урон по самому провоцирующему НЕ снижается
    guardian2 = combatant(4, side=0, subclass_id="guardian")
    enemy2 = combatant(5, side=1)
    state2 = make_session(CombatMode.PVP_GROUP, guardian2, enemy2)
    resolve_tick(state2, {4: skill("guardian_provoke"), 5: attack(4)}, rng)
    assert guardian2.max_hp - guardian2.current_hp == baseline


def test_freeze_skips_action() -> None:
    rng = NoCritRng()
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    a.effects.append(Effect(kind=EffectKind.FREEZE, value=1, remaining_ticks=1, source_id=2))
    state = make_session(CombatMode.PVP_GROUP, a, b)
    result = resolve_tick(state, {1: attack(2)}, rng)
    assert b.current_hp == b.max_hp  # атака не состоялась
    assert any("скован" in line for line in result.lines)
    assert not a.has_effect(EffectKind.FREEZE)  # эффект оттикал


def test_dot_ticks_damage() -> None:
    rng = NoCritRng()
    a = combatant(1, side=0)
    b = combatant(2, side=1)
    b.effects.append(Effect(kind=EffectKind.DOT, value=25, remaining_ticks=2, source_id=1))
    state = make_session(CombatMode.PVP_GROUP, a, b)
    resolve_tick(state, {}, rng)
    assert b.current_hp == b.max_hp - 25
    assert b.has_effect(EffectKind.DOT)  # остался 1 тик
