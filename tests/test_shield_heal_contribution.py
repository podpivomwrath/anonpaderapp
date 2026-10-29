"""Остаток Оберега, обращённый в лечение, засчитывается мистику в итоге
рейда (2026-10-29, баг-репорт: в таблице вклада его не было)."""

import random

from bot.handlers import raid_combat, raid_results
from game.combat.resolver import resolve_tick
from game.combat.session import WARD_TAG, CombatMode, CombatSessionState, EffectKind
from tests.conftest import combatant


def test_ward_leftover_heal_counts_for_the_mystic() -> None:
    mystic = combatant(1, side=0, subclass_id="dark_mystic")
    ally = combatant(2, side=0)
    mob = combatant(3, side=1, kind="mob")
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    for c in (mystic, ally, mob):
        state.add(c)
    ally.current_hp = ally.max_hp - 100
    ally.apply_effect(EffectKind.SHIELD_POOL, 60, 1, mystic.id, tag=WARD_TAG)
    # Щит висит с прошлого хода: этот ход его последний.
    result = resolve_tick(state, {}, random.Random(1))
    assert (mystic.id, ally.id, 60) in result.shield_heals

    battle = raid_combat.RaidBattle(
        group_id=None, participants={1: object(), 2: object()}, member_inputs=[], rng=random.Random(1),
    )
    raid_results._record_contribution(battle, result)
    assert battle.contribution[mystic.id].healed >= 60
