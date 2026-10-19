"""Ход против мобов по фазам (2026-10-19): сначала игроки, потом мобы.
В PvP ход по-прежнему одновременный."""

from game.combat import battle_log
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType, CombatMode, CombatSessionState, DeclaredAction, Effect, EffectKind,
)
from game.combat.skills import PendingHeal
from tests.conftest import NoCritRng, combatant

ATTACK = lambda t: DeclaredAction(type=ActionType.ATTACK, target_id=t)  # noqa: E731


def _session(mode, *cs):
    state = CombatSessionState(session_id=1, mode=mode, is_raid=True)
    for c in cs:
        state.add(c)
    return state


def test_heal_lands_at_turn_end_and_log_reads_in_order() -> None:
    tank = combatant(1, 0, name="Страж", level=30, subclass_id="guardian")
    healer = combatant(2, 0, name="Мистик", level=30, subclass_id="dark_mystic")
    wolf = combatant(10, 1, kind="mob", name="Волк", level=30, strength=200)
    tank.current_hp = tank.max_hp // 2
    wolf.taunted_by, wolf.taunt_left = tank.id, 2
    state = _session(CombatMode.PVE, tank, healer, wolf)
    res = resolve_tick(state, {
        1: ATTACK(10),
        2: DeclaredAction(type=ActionType.SKILL, skill_id="dark_mystic_blood_pact", target_id=1),
    }, NoCritRng())
    heal = next(h for h in res.heal_renders if h.target_id == 1)
    wolf_hit = next(h for h in res.hit_renders if h.source_id == 10)
    # Удар волка, затем лечение: цифры идут подряд.
    assert heal.hp_before == wolf_hit.hp_after
    assert heal.hp_after == tank.current_hp
    board = battle_log.render_tick(state, res)
    assert board.index("Волк →") < board.index("📋 ИТОГ ХОДА") < board.index("восполнено")


def test_turn_end_heal_still_saves_from_a_lethal_hit() -> None:
    """Лечение доходит одной суммой с ударом моба - спасает, как и раньше."""
    tank = combatant(1, 0, level=30)
    wolf = combatant(10, 1, kind="mob", level=30, strength=200)
    state = _session(CombatMode.PVE, tank, wolf)
    tank.current_hp = 5
    wolf.taunted_by, wolf.taunt_left = tank.id, 2

    from game.combat import resolver

    original = resolver._run_offensive

    def heal_instead(ctx, cid, action, session, result):
        ctx.heals.append(PendingHeal(source_id=cid, target_id=cid, amount=tank.max_hp))

    resolver._run_offensive = heal_instead
    try:
        res = resolve_tick(state, {1: ATTACK(10)}, NoCritRng())
    finally:
        resolver._run_offensive = original
    assert tank.alive and 1 not in res.deaths


def test_mob_killed_by_players_takes_no_dot_and_strikes_nobody() -> None:
    hero = combatant(1, 0, level=30, strength=400)
    wolf = combatant(10, 1, kind="mob", level=30)
    wolf.current_hp = 1
    wolf.effects.append(Effect(kind=EffectKind.DOT, value=50, remaining_ticks=3, source_id=1))
    state = _session(CombatMode.PVE, hero, wolf)
    res = resolve_tick(state, {1: ATTACK(10)}, NoCritRng())
    assert not wolf.alive
    assert not any(h.is_tick for h in res.hit_renders)
    assert not any(h.source_id == 10 for h in res.hit_renders)
    assert hero.current_hp == hero.max_hp


def test_deaths_and_dots_go_to_turn_summary_in_pve() -> None:
    hero = combatant(1, 0, level=30, strength=400)
    wolf = combatant(10, 1, kind="mob", name="Волк", level=30)
    wolf.current_hp = 1
    state = _session(CombatMode.PVE, hero, wolf)
    res = resolve_tick(state, {1: ATTACK(10)}, NoCritRng())
    board = battle_log.render_tick(state, res)
    assert "📋 ИТОГ ХОДА" in board
    assert board.index("📋 ИТОГ ХОДА") < board.index("☠ Волк погибает")


def test_pvp_group_stays_simultaneous() -> None:
    a = combatant(1, 0, level=30, strength=200)
    b = combatant(2, 1, level=30, strength=200)
    a.current_hp = b.current_hp = 5
    state = _session(CombatMode.PVP_GROUP, a, b)
    res = resolve_tick(state, {1: ATTACK(2), 2: ATTACK(1)}, NoCritRng())
    assert not a.alive and not b.alive and res.draw
    assert "📋 ИТОГ ХОДА" not in battle_log.render_tick(state, res)
