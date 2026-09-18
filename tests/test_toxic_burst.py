"""Токсический выброс: перенос оставшегося урона яда, а не потеря.

Раньше урон считался как доля ОДНОГО тика, при этом яд уничтожался целиком:
283 урона вместо 453, которые тот же яд принёс бы сам, плюс потраченный ход и
перезарядка 5. Навык был чистой потерей - применять его не имело смысла
никогда. Вдобавок он считал от БАЗОВОГО тика и молча игнорировал баффы урона
яда: игрок качал «Разъедающий токсин» с «Некрозом», видел растущие тики, а
финишер не рос.
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
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from tests.conftest import NoCritRng, combatant


def _burst_damage(*, stacks: int = 3, ticks: int = 4, mods: dict | None = None) -> int:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=57, agility=91)
    poisoner.buff_modifiers = dict(mods or {})
    enemy = combatant(2, side=1, vitality=5000, agility=0)
    per_stack = (
        bc.POISONER_POISON_WIL_COEF * 57 + bc.POISONER_POISON_AGI_COEF * 91
    ) / bc.POISONER_MAX_STACKS
    enemy.effects.append(
        Effect(kind=EffectKind.DOT, value=per_stack, remaining_ticks=ticks,
               source_id=poisoner.id, stacks=stacks)
    )
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    state.tick_number = 1
    before = enemy.current_hp
    resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        rng,
    )
    return before - enemy.current_hp


def _total_over_fight(*, use_burst: bool, ticks: int = 4, stacks: int = 3,
                      mods: dict | None = None) -> int:
    """Суммарный урон за всю жизнь яда - с выбросом и без.

    Сравнивать один удар выброса с полным остатком яда нельзя: перенесённая
    часть сгорает, а ОСТАТОК продолжает тикать. Правильная проверка - сколько
    урона набежало за весь бой.
    """
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=57, agility=91)
    poisoner.buff_modifiers = dict(mods or {})
    enemy = combatant(2, side=1, vitality=50000, agility=0)
    per_stack = (
        bc.POISONER_POISON_WIL_COEF * 57 + bc.POISONER_POISON_AGI_COEF * 91
    ) / bc.POISONER_MAX_STACKS
    enemy.effects.append(
        Effect(kind=EffectKind.DOT, value=per_stack, remaining_ticks=ticks,
               source_id=poisoner.id, stacks=stacks)
    )
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    before = enemy.current_hp
    for turn in range(ticks + 1):
        state.tick_number = turn + 1
        action = (
            DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)
            if use_burst and turn == 0
            else DeclaredAction(type=ActionType.SKIP)
        )
        resolve_tick(state, {1: action}, rng)
    return before - enemy.current_hp


def test_burst_is_never_a_loss() -> None:
    """Главный баг: навык уничтожал больше урона, чем наносил."""
    for ticks in (1, 2, 3, 4):
        with_burst = _total_over_fight(use_burst=True, ticks=ticks)
        without = _total_over_fight(use_burst=False, ticks=ticks)
        assert with_burst >= without, f"осталось {ticks} ходов: {with_burst} < {without}"


def test_burst_leaves_the_rest_of_the_poison_ticking() -> None:
    """Переносится не больше потолка - остаток обязан остаться на цели,
    иначе выброс снова съедал бы больше, чем наносит."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1, vitality=50000, agility=0)
    enemy.effects.append(
        Effect(kind=EffectKind.DOT, value=10.0,
               remaining_ticks=bc.POISONER_BURST_MAX_TICKS + 2, source_id=1, stacks=2)
    )
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    state.tick_number = 1
    resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        rng,
    )
    assert enemy.has_effect(EffectKind.DOT)


def test_burst_scales_with_remaining_duration_up_to_the_cap() -> None:
    assert _burst_damage(ticks=bc.POISONER_BURST_MAX_TICKS) > _burst_damage(ticks=1)


def test_burst_respects_poison_damage_buffs() -> None:
    """«Разъедающий токсин» и «Некроз» поднимают тик - финишер обязан расти
    вместе с ним, иначе прокачка урона яда его не касается."""
    plain = _burst_damage()
    corroding = _burst_damage(mods={"poison_damage_bonus": bc.POISONER_CORRODING_TOXIN_BONUS})
    necrosis = _burst_damage(mods={"poison_damage_per_stack": bc.POISONER_NECROSIS_PER_STACK})
    assert corroding > plain
    assert necrosis > plain


def test_burst_scales_with_stacks() -> None:
    assert _burst_damage(stacks=3) > _burst_damage(stacks=1)


def test_burst_consumes_a_short_poison_entirely() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1, vitality=5000, agility=0)
    enemy.effects.append(
        Effect(kind=EffectKind.DOT, value=10.0,
               remaining_ticks=bc.POISONER_BURST_MAX_TICKS, source_id=1, stacks=2)
    )
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    state.tick_number = 1
    resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        rng,
    )
    assert not enemy.has_effect(EffectKind.DOT)


def test_burst_without_poison_does_nothing() -> None:
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    enemy = combatant(2, side=1, vitality=5000, agility=0)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    state.tick_number = 1
    before = enemy.current_hp
    result = resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        rng,
    )
    assert enemy.current_hp == before
    assert any("нет яда" in line for line in result.lines)


def test_bonus_multiplier_is_above_one() -> None:
    """Множитель применяется к ОСТАТКУ урона яда: ниже единицы он снова
    превратил бы навык в размен себе в убыток."""
    assert SUBCLASS_SKILL_DEFS["poisoner_toxic_burst"].effect_value > 1.0
