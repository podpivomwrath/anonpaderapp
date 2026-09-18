"""Патч 56: микробаффы Клинка теней (крит/уворот/Метка добычи)."""

from game.combat import balance_config as bc
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


class AlwaysLowRng(NoCritRng):
    def random(self) -> float:
        return 0.0


class DodgeRng(NoCritRng):
    """Ниже общего потолка уворота, но выше шанса крита: проверяем уворот,
    не задевая криты. Потолок DODGE_HARD_CAP делает «гарантированный» уворот
    невозможным в принципе - именно поэтому нельзя просто взять 0.999."""

    def random(self) -> float:
        return bc.DODGE_HARD_CAP - 0.05


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def mark(target, source_id: int, stacks: int) -> Effect:
    effect = Effect(kind=EffectKind.MARK, value=1.0,
                    remaining_ticks=bc.SHADOW_BLADE_MARK_DURATION,
                    source_id=source_id, stacks=stacks)
    target.effects.append(effect)
    return effect


# --- Крит ---


def test_deadly_precision_raises_crit_chance() -> None:
    """Шанс крита читается из buff_modifiers: с бонусом 100% крит гарантирован
    даже при rng, который сам по себе крит не выдаёт."""
    rng = NoCritRng()  # random() = 0.999
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    blade.buff_modifiers = {"crit_chance_bonus": 1.0}
    enemy = combatant(2, side=1, agility=0, vitality=500)
    result = resolve_tick(make_session(blade, enemy), {1: attack(2)}, rng)
    assert any(h.crit for h in result.hits if h.source_id == blade.id)


def test_bloodlust_guarantees_crit_after_crit() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    blade.buff_modifiers = {
        "crit_chance_bonus": 1.0,
        "bloodlust_cooldown": float(bc.SHADOW_BLADE_BLOODLUST_COOLDOWN),
    }
    enemy = combatant(2, side=1, agility=0, vitality=500)
    state = make_session(blade, enemy)
    state.tick_number = 1
    resolve_tick(state, {1: attack(2)}, rng)
    assert blade.guaranteed_crit_next is True  # крит был - следующий гарантирован


def test_carve_boosts_crit_multiplier_only_with_enough_stacks() -> None:
    from game.content_loader import load_content

    buff = load_content().buffs["shadow_blade_carve"]
    assert buff.stat_modifiers["carve_crit_mult"] == bc.SHADOW_BLADE_CARVE_CRIT_MULT
    assert bc.SHADOW_BLADE_CARVE_CRIT_MULT > bc.CRIT_MULTIPLIER
    assert bc.SHADOW_BLADE_CARVE_MIN_STACKS == 3  # текст патча


def test_mark_of_prey_plus_adds_stack_from_basic_attack() -> None:
    rng = AlwaysLowRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    blade.buff_modifiers = {"mark_on_attack_chance": 1.0}
    enemy = combatant(2, side=1, agility=0, vitality=500)
    resolve_tick(make_session(blade, enemy), {1: attack(2)}, rng)
    assert enemy.effect_from(EffectKind.MARK, blade.id) is not None


# --- Уклонение ---


def test_shadow_adds_dodge() -> None:
    rng = DodgeRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=0)
    blade.buff_modifiers = {"dodge_bonus": 1.0}  # гарантированный уворот
    enemy = combatant(2, side=1)
    result = resolve_tick(make_session(blade, enemy), {2: attack(1)}, rng)
    assert any(h.missed for h in result.hits if h.target_id == blade.id)


def test_second_chance_forces_miss_on_schedule() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=0)
    blade.buff_modifiers = {"second_chance_interval": float(bc.SHADOW_BLADE_SECOND_CHANCE_INTERVAL)}
    enemy = combatant(2, side=1)
    state = make_session(blade, enemy)
    state.tick_number = bc.SHADOW_BLADE_SECOND_CHANCE_INTERVAL  # кратный ход
    result = resolve_tick(state, {2: attack(1)}, rng)
    assert any(h.missed for h in result.hits if h.target_id == blade.id)


def test_blade_hunger_adds_mark_on_successful_dodge() -> None:
    rng = DodgeRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=0)
    blade.buff_modifiers = {"dodge_bonus": 1.0, "mark_on_dodge": 1.0}
    enemy = combatant(2, side=1)
    resolve_tick(make_session(blade, enemy), {2: attack(1)}, rng)
    assert enemy.effect_from(EffectKind.MARK, blade.id) is not None


def test_slip_away_remembers_previous_dodge() -> None:
    rng = DodgeRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=0)
    blade.buff_modifiers = {"dodge_bonus": 1.0, "slip_away_bonus": bc.SHADOW_BLADE_SLIP_AWAY}
    enemy = combatant(2, side=1)
    state = make_session(blade, enemy)
    resolve_tick(state, {2: attack(1)}, rng)
    assert blade.dodged_last_tick is True  # следующий ход получит бонус


# --- Соло и группа ---


def test_hunters_solitude_only_without_allies() -> None:
    rng = NoCritRng()

    def damage(with_ally: bool) -> int:
        blade = combatant(1, side=0, subclass_id="shadow_blade")
        blade.buff_modifiers = {"solo_damage_bonus": bc.SHADOW_BLADE_SOLO_DAMAGE}
        enemy = combatant(2, side=1, vitality=500, agility=0)
        parts = [blade, enemy] + ([combatant(3, side=0)] if with_ally else [])
        before = enemy.current_hp
        resolve_tick(make_session(*parts), {1: attack(2)}, rng)
        return before - enemy.current_hp

    assert damage(with_ally=False) > damage(with_ally=True)


def test_inspiration_heals_allies_on_marked_kill() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    blade.buff_modifiers = {
        "inspiration_heal_pct": bc.SHADOW_BLADE_INSPIRATION_HEAL,
        "inspiration_damage_bonus": bc.SHADOW_BLADE_INSPIRATION_DAMAGE,
    }
    ally = combatant(3, side=0)
    ally.current_hp = int(ally.max_hp * 0.5)
    hp_before = ally.current_hp
    victim = combatant(2, side=1, agility=0)
    victim.current_hp = 1
    mark(victim, source_id=blade.id, stacks=2)

    resolve_tick(make_session(blade, ally, victim), {1: attack(2)}, rng)

    assert ally.current_hp > hp_before
    assert ally.has_effect(EffectKind.DAMAGE_BUFF)


def test_mark_passed_on_helps_only_allies() -> None:
    """Бонус крита по помеченной цели даётся союзнику, а не самому владельцу
    Метки: ключ читается у бьющего, а метка должна быть от ДРУГОГО."""
    rng = NoCritRng()
    ally = combatant(3, side=0)
    ally.buff_modifiers = {"mark_ally_crit_bonus": 1.0}  # гарантированный крит
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    enemy = combatant(2, side=1, agility=0, vitality=500)
    mark(enemy, source_id=blade.id, stacks=1)

    result = resolve_tick(make_session(blade, ally, enemy), {3: attack(2)}, rng)
    assert any(h.crit for h in result.hits if h.source_id == ally.id)


def test_hunting_mark_shows_stacks_in_battle_board() -> None:
    """«Клеймо охоты»: стаки Метки видны всей стороне в сводке HP, без баффа
    сводка остаётся прежней."""
    from game.combat.battle_log import render_tick

    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    ally = combatant(3, side=0)
    enemy = combatant(2, side=1, agility=0, vitality=500)
    mark(enemy, source_id=blade.id, stacks=2)
    state = make_session(blade, ally, enemy)
    result = resolve_tick(state, {}, rng)

    assert "Метка добычи ×2" not in render_tick(state, result, viewer_side=0)
    blade.buff_modifiers = {"mark_visible_to_allies": 1.0}
    assert "Метка добычи ×2" in render_tick(state, result, viewer_side=0)
    # Противник свою метку в своей сводке не видит
    assert "Метка добычи" not in render_tick(state, result, viewer_side=1)
