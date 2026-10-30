"""Манекен арены (2026-10-30): 99999 здоровья, не бьёт, босс не поддаётся
контролю, моб - поддаётся."""

import random

from game.combat import control
from game.combat.resolver import resolve_tick
from game.combat.session import CombatMode, CombatSessionState
from game.world import arena_dummy
from tests.conftest import combatant


def test_dummy_kinds():
    boss = arena_dummy.build(2, arena_dummy.BOSS, 30)
    mob = arena_dummy.build(2, arena_dummy.MOB, 30)
    assert boss.max_hp == boss.current_hp == mob.max_hp == arena_dummy.HP
    assert boss.control_immune_always and not mob.control_immune_always
    assert mob.level == 30
    rng = random.Random(1)
    assert control.try_apply_control(boss, 2, 1, rng, pvp=False).reason == "always"
    assert any(control.try_apply_control(mob, 2, 1, random.Random(s), pvp=False).applied for s in range(20))


def test_dummy_never_hits_back():
    for kind in (arena_dummy.BOSS, arena_dummy.MOB):
        state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
        player = combatant(1, side=0, name="Игрок")
        state.add(player)
        state.add(arena_dummy.build(2, kind, 30))
        hp = player.current_hp
        for _ in range(arena_dummy.TURNS):
            resolve_tick(state, {}, random.Random(1))
        assert player.current_hp == hp
