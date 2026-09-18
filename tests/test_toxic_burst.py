"""Токсический выброс обязан соответствовать своему описанию:

    «Взрывает весь яд на цели: урон - 250% от суммарного тик-урона этого яда.
     Стаки сгорают.»

Отсюда три проверяемых обещания: считается ВЕСЬ настаканный яд, множитель
берётся от РЕАЛЬНОГО тик-урона (а он растёт от «Разъедающего токсина» и
«Некроза»), и после применения яда на цели не остаётся.

Раньше сила бралась из СЫРОГО значения эффекта мимо общего правила: тик рос со
113 до 169, а финишер считал от 113 - прокачка урона яда его не касалась.
"""

from game.combat import balance_config as bc
from game.combat import shared_rules
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

WIL, AGI = 57, 91


def _setup(*, stacks: int = 3, ticks: int = 4, mods: dict | None = None):
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=WIL, agility=AGI)
    poisoner.buff_modifiers = dict(mods or {})
    enemy = combatant(2, side=1, vitality=50000, agility=0)
    per_stack = (
        bc.POISONER_POISON_WIL_COEF * WIL + bc.POISONER_POISON_AGI_COEF * AGI
    ) / bc.POISONER_MAX_STACKS
    poison = Effect(kind=EffectKind.DOT, value=per_stack, remaining_ticks=ticks,
                    source_id=poisoner.id, stacks=stacks)
    enemy.effects.append(poison)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(enemy)
    state.tick_number = 1
    return poisoner, enemy, poison, state


def _burst(**kwargs) -> tuple[int, object, object]:
    poisoner, enemy, poison, state = _setup(**kwargs)
    expected_tick = shared_rules.poison_tick_damage(poison, poisoner)
    result = resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        NoCritRng(),
    )
    dealt = next((h.amount for h in result.hits if h.label == "взрывает ядом"), 0)
    return dealt, expected_tick, (enemy, result)


def test_damage_is_the_promised_share_of_the_whole_tick() -> None:
    """250% от суммарного тик-урона - ровно то число, что обещано игроку."""
    multiplier = SUBCLASS_SKILL_DEFS["poisoner_toxic_burst"].effect_value
    for stacks in (1, 2, 3):
        dealt, tick, _ = _burst(stacks=stacks)
        assert dealt == round(tick * multiplier), f"{stacks} стака"


def test_all_stacks_are_counted() -> None:
    """«Суммарный» значит по ВСЕМ стакам: три стака бьют втрое сильнее одного.

    Округление одно - на итог, а не на каждый стак, поэтому сравниваем с
    допуском в пару единиц, а не на точное равенство.
    """
    one, _, _ = _burst(stacks=1)
    three, _, _ = _burst(stacks=3)
    assert abs(three - 3 * one) <= 3


def test_poison_damage_buffs_raise_the_burst() -> None:
    plain, _, _ = _burst()
    corroding, _, _ = _burst(mods={"poison_damage_bonus": bc.POISONER_CORRODING_TOXIN_BONUS})
    necrosis, _, _ = _burst(mods={"poison_damage_per_stack": bc.POISONER_NECROSIS_PER_STACK})
    assert corroding > plain
    assert necrosis > plain


def test_whole_poison_burns_regardless_of_duration() -> None:
    """«Стаки сгорают» - весь эффект, сколько бы ходов ему ни оставалось."""
    for ticks in (1, 4):
        _, _, (enemy, _) = _burst(ticks=ticks)
        assert not enemy.has_effect(EffectKind.DOT), f"осталось {ticks} ходов"


def test_burst_is_the_players_action_not_a_passive_tick() -> None:
    """Выброс идёт мимо уворота и крита, как ДоТ, но это ДЕЙСТВИЕ игрока.

    Пока флаг был один, лог печатал его в разделе ПРОТИВНИКА строкой «теряет
    N HP от эффекта», а сторона игрока в этот ход показывала «Без изменений».
    """
    from game.combat.battle_log import render_tick

    poisoner, enemy, _, state = _setup()
    result = resolve_tick(
        state,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="poisoner_toxic_burst", target_id=2)},
        NoCritRng(),
    )
    burst = next(h for h in result.hit_renders if h.label == "взрывает ядом")
    assert burst.is_dot is True     # механика: мимо уворота и крита
    assert burst.is_tick is False   # отображение: это ход игрока

    board = render_tick(state, result, viewer_side=0).split("\n")
    own = board.index("👥 ВАША СТОРОНА")
    enemy_header = board.index("💀 ПРОТИВНИК")
    line = next(i for i, text in enumerate(board) if "взрывает ядом" in text)
    assert own < line < enemy_header
    assert "Без изменений." not in board[own + 1]


def test_real_dot_ticks_stay_in_the_targets_section() -> None:
    """Обычный тик яда - по-прежнему пассивный эффект, а не чьё-то действие."""
    from game.combat.battle_log import render_tick

    _, enemy, _, state = _setup()
    result = resolve_tick(state, {}, NoCritRng())
    tick = next(h for h in result.hit_renders if h.is_tick)
    assert tick.is_tick is True
    board = render_tick(state, result, viewer_side=0)
    assert "теряет" in board and "от эффекта" in board


def test_burst_without_poison_does_nothing() -> None:
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
        NoCritRng(),
    )
    assert enemy.current_hp == before
    assert any("нет яда" in line for line in result.lines)
