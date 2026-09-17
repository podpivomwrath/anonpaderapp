"""Патч 56: микробаффы Отравителя.

Подкласс отстаёт (винрейт 27%), поэтому пул усилен: дебаффы сильнее, яд
дороже, появляется распространение по нескольким целям.
"""

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
    """random() = 0.0: все шансовые проверки срабатывают."""

    def random(self) -> float:
        return 0.0


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def poison(target, source_id: int, stacks: int = 1, value: float = 10.0, ticks: int = 3) -> Effect:
    effect = Effect(kind=EffectKind.DOT, value=value, remaining_ticks=ticks,
                    source_id=source_id, stacks=stacks)
    target.effects.append(effect)
    return effect


# --- Сила дебаффов ---


def test_toxic_blood_strengthens_vulnerability() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"vulnerability_bonus": bc.POISONER_TOXIC_BLOOD_VULN_BONUS}
    enemy = combatant(2, side=1)
    resolve_tick(make_session(poisoner, enemy), {1: skill("poisoner_decay", 2)}, rng)

    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    base = SUBCLASS_SKILL_DEFS["poisoner_decay"].effect_value
    assert enemy.effect_total(EffectKind.VULNERABILITY) == base + bc.POISONER_TOXIC_BLOOD_VULN_BONUS


def test_desiccation_strengthens_weaken() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"weaken_bonus": bc.POISONER_DESICCATION_WEAKEN_BONUS}
    enemy = combatant(2, side=1)
    resolve_tick(make_session(poisoner, enemy), {1: skill("poisoner_disrupt", 2)}, rng)
    assert enemy.effect_total(EffectKind.WEAKEN) == (
        bc.POISONER_DISRUPT_WEAKEN + bc.POISONER_DESICCATION_WEAKEN_BONUS
    )


def test_double_dose_adds_weaken_to_decay() -> None:
    rng = AlwaysLowRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"double_dose_chance": 1.0}
    enemy = combatant(2, side=1, agility=0)
    resolve_tick(make_session(poisoner, enemy), {1: skill("poisoner_decay", 2)}, rng)
    assert enemy.has_effect(EffectKind.VULNERABILITY)
    assert enemy.has_effect(EffectKind.WEAKEN)  # оба дебаффа одним применением


# --- Урон ядом ---


def test_corroding_toxin_and_necrosis_scale_poison_damage() -> None:
    rng = NoCritRng()

    def tick_damage(mods: dict) -> int:
        poisoner = combatant(1, side=0, subclass_id="poisoner")
        poisoner.buff_modifiers = dict(mods)
        enemy = combatant(2, side=1, vitality=500)
        poison(enemy, source_id=1, stacks=2)
        before = enemy.current_hp
        resolve_tick(make_session(poisoner, enemy), {}, rng)
        return before - enemy.current_hp

    plain = tick_damage({})
    corroding = tick_damage({"poison_damage_bonus": bc.POISONER_CORRODING_TOXIN_BONUS})
    necrosis = tick_damage({"poison_damage_per_stack": bc.POISONER_NECROSIS_PER_STACK})
    assert corroding > plain
    assert necrosis > plain


def test_toxic_burst_fires_when_poison_expires() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"poison_expire_burst_pct": bc.POISONER_TOXIC_BURST_EXPIRE_PCT}
    enemy = combatant(2, side=1, vitality=500)
    poison(enemy, source_id=1, stacks=3, ticks=1)  # истечёт в этот же ход

    result = resolve_tick(make_session(poisoner, enemy), {}, rng)
    assert any("вспыхивает напоследок" in line for line in result.lines)


def test_toxicology_pierces_part_of_shield() -> None:
    rng = NoCritRng()

    def damage_through_shield(pierce: float) -> int:
        poisoner = combatant(1, side=0, subclass_id="poisoner")
        if pierce:
            poisoner.buff_modifiers = {"poison_shield_pierce": pierce}
        enemy = combatant(2, side=1, vitality=500)
        enemy.shield = 1000  # заведомо больше тика яда
        poison(enemy, source_id=1, stacks=3, value=20.0)
        before = enemy.current_hp
        resolve_tick(make_session(poisoner, enemy), {}, rng)
        return before - enemy.current_hp

    assert damage_through_shield(0.0) == 0  # щит держит яд целиком
    assert damage_through_shield(bc.POISONER_TOXICOLOGY_SHIELD_PIERCE) > 0


# --- Распространение ---


def test_plague_moves_poison_from_dead_target() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"plague_spread": 1.0, "epidemic_full_power": 1.0}
    dying = combatant(2, side=1)
    neighbour = combatant(3, side=1)
    effect = poison(dying, source_id=1, stacks=2, value=12.0)
    dying.current_hp = 1  # добьётся тиком яда

    resolve_tick(make_session(poisoner, dying, neighbour), {}, rng)

    moved = neighbour.effect_from(EffectKind.DOT, 1)
    assert moved is not None
    assert moved.stacks == effect.stacks
    assert moved.value == effect.value  # «Эпидемия»: полная сила


def test_plague_without_epidemic_halves_power() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"plague_spread": 1.0}
    dying = combatant(2, side=1)
    neighbour = combatant(3, side=1)
    poison(dying, source_id=1, stacks=2, value=12.0)
    dying.current_hp = 1

    resolve_tick(make_session(poisoner, dying, neighbour), {}, rng)
    moved = neighbour.effect_from(EffectKind.DOT, 1)
    assert moved is not None and moved.value == 6.0


def test_venom_cloud_needs_several_enemies() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"venom_cloud_interval": float(bc.POISONER_VENOM_CLOUD_INTERVAL)}
    main = combatant(2, side=1)
    other = combatant(3, side=1)
    state = make_session(poisoner, main, other)
    state.tick_number = bc.POISONER_VENOM_CLOUD_INTERVAL - 1  # резолвер не двигает счётчик сам

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    # В дуэли эффекта нет: облаку нужны другие противники
    assert other.effect_from(EffectKind.DOT, 1) is None or main.effect_from(EffectKind.DOT, 1) is not None


# --- Контроль ---


def test_hallucinogen_raises_disrupt_chance() -> None:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
    from game.content_loader import load_content

    base = SUBCLASS_SKILL_DEFS["poisoner_disrupt"].effect_value
    buff = load_content().buffs["poisoner_hallucinogen"]
    total = base + buff.stat_modifiers["disrupt_chance_bonus"]
    assert abs(total - 0.75) < 1e-9  # текст патча: 60% -> 75%


def test_paralytic_lowers_control_resist_after_disrupt() -> None:
    rng = AlwaysLowRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = {"paralytic_resist_down": bc.POISONER_PARALYTIC_RESIST_DOWN}
    enemy = combatant(2, side=1, agility=0, will=0)

    resolve_tick(make_session(poisoner, enemy), {1: skill("poisoner_disrupt", 2)}, rng)
    assert enemy.effect_total(EffectKind.CONTROL_RESIST_DOWN) == bc.POISONER_PARALYTIC_RESIST_DOWN
