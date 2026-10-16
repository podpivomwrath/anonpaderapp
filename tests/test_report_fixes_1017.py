"""Правки 2026-10-17: блок виден в каждом ударе, опыт рейда - как в разломе."""

from types import SimpleNamespace

from game.combat import battle_log
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.economy import raid_config as rc
from tests.conftest import NoCritRng, combatant


def test_block_shown_on_every_hit_of_the_stance():
    guard = combatant(1, 0, subclass_id="guardian", vitality=60)
    mob = combatant(2, 1, kind="mob", name="Моб", strength=40, vitality=200)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    state.add(guard)
    state.add(mob)
    block = DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block", target_id=2)
    skip = DeclaredAction(type=ActionType.SKIP)
    for action in (block, skip, skip):
        result = resolve_tick(state, {1: action}, NoCritRng())
        hit = next(h for h in result.hit_renders if h.target_id == 1)
        assert hit.blocked > 0
        assert "блок срезал" in battle_log._hit_line(hit, "Моб", guard.name, "pve")


def test_raid_xp_per_stage_not_split():
    from bot.handlers import raid_combat

    battle = SimpleNamespace(is_rift=False, stage=3)
    assert raid_combat._xp_mobs(battle) == rc.RAID_STAGE_XP_MOBS[3]
