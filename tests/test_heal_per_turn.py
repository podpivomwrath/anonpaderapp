"""Лечебное зелье - одно за ход (2026-10-19): ход не тратит, лимит 10 за бой
прежний. Отметка сбрасывается вместе с остальным состоянием хода."""

from types import SimpleNamespace

from game.combat import consumable_limit as cl
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from tests.conftest import NoCritRng, combatant

HEAL = SimpleNamespace(category="heal", id="heal_small")
FEVER = SimpleNamespace(category="combat", id="ashen_fever")


def test_second_heal_hidden_until_next_turn() -> None:
    hero = combatant(1, 0, level=30)
    stock = [(HEAL, 5), (FEVER, 2)]
    assert cl.visible_stock(hero, stock, False) == stock
    cl.mark_heal(hero)
    assert cl.heal_taken(hero)
    assert cl.visible_stock(hero, stock, False) == [(FEVER, 2)]
    assert cl.HEAL_TAKEN_TEXT in cl.items_header(hero)
    hero.reset_transient()
    assert not cl.heal_taken(hero)


def test_tick_resets_the_heal_mark() -> None:
    hero = combatant(1, 0, level=30)
    wolf = combatant(10, 1, kind="mob", level=30)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    state.add(hero)
    state.add(wolf)
    cl.mark_heal(hero)
    resolve_tick(state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=10)}, NoCritRng())
    assert not cl.heal_taken(hero)


def test_battle_limit_still_hides_everything() -> None:
    hero = combatant(1, 0, level=30)
    hero.consumables_used = cl.LIMIT
    assert cl.visible_stock(hero, [(HEAL, 5)], False) == []
    assert cl.LIMIT == 10
