"""Репорт #79 (2026-10-16): моб выше уровнем, которого удар «на бумаге»
добивал, а с поправкой за уровни - нет, пропускал свой ход."""

from game.combat import formulas
from game.combat.resolver import _dies_this_tick
from game.combat.session import CombatMode, CombatSessionState
from game.combat.skills import PendingHit
from tests.conftest import combatant


def _session(*cs):
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    for c in cs:
        state.combatants[c.id] = c
    return state


def test_level_diff_is_counted_before_skipping_mob_turn():
    player = combatant(1, side=0, level=33)
    mob = combatant(2, side=1, kind="mob", level=40)
    session = _session(player, mob)
    raw = 362
    _, taken = formulas.level_diff_modifiers(mob.level, player.level)
    assert taken < 1
    mob.current_hp = raw  # «сырой» удар добивает ровно в ноль, реальный - нет
    hit = PendingHit(source_id=player.id, target_id=mob.id, amount=raw, label="Кровопуск")
    assert _dies_this_tick(mob, [hit]) is True          # старое поведение
    assert _dies_this_tick(mob, [hit], session) is False  # с поправкой - выживет и ходит
    mob.current_hp = round(raw * taken)
    assert _dies_this_tick(mob, [hit], session) is True
