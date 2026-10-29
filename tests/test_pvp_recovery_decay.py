"""PvP: лечение и щиты слабеют от 100% в первый ход до 30% в последний
(2026-10-29, владелец); щит виден в строке удара лога хода."""

from game.combat import balance_config as bc
from game.combat import battle_log, shared_rules
from game.combat.resolver import RenderedHit
from game.combat.session import ECHO_TAG, EffectKind, CombatSessionState, CombatMode
from tests.conftest import combatant as make_combatant


def test_recovery_mult_runs_from_full_to_floor() -> None:
    turns = bc.PVP_MAX_TURNS
    assert shared_rules.recovery_mult(1, turns) == 1.0
    assert shared_rules.recovery_mult(turns, turns) == bc.PVP_RECOVERY_FLOOR == 0.3
    mid = shared_rules.recovery_mult(turns // 2, turns)
    assert bc.PVP_RECOVERY_FLOOR < mid < 1.0
    # Вне PvP (лимита ходов нет) - всегда в полную силу.
    assert shared_rules.recovery_mult(50, None) == 1.0


def test_shield_and_heal_scaled_by_turn() -> None:
    session = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    c = make_combatant(1, side=0)
    session.add(c)
    session.tick_number = bc.PVP_MAX_TURNS
    shared_rules.set_recovery(session, bc.PVP_MAX_TURNS)
    c.apply_effect(EffectKind.SHIELD_POOL, 500, 3, c.id)
    assert sum(e.value for e in c.effects_of(EffectKind.SHIELD_POOL)) == 150
    assert shared_rules.recovered(c, 300) == 90

    session.tick_number = 1
    shared_rules.set_recovery(session, bc.PVP_MAX_TURNS)
    c.apply_effect(EffectKind.SHIELD_POOL, 500, 3, c.id, tag="ward")
    assert sum(e.value for e in c.effects_of(EffectKind.SHIELD_POOL)) == 150 + 500
    assert shared_rules.recovered(c, 300) == 300


def test_echo_shield_not_cut_twice() -> None:
    c = make_combatant(1, side=0)
    c.recovery_mult = 0.5
    c.apply_effect(EffectKind.SHIELD_POOL, 400, 3, c.id, tag=ECHO_TAG)
    assert sum(e.value for e in c.effects_of(EffectKind.SHIELD_POOL)) == 400


def test_log_line_shows_shield() -> None:
    hit = RenderedHit(
        source_id=1, target_id=2, source_side=0, target_side=1, label="attack", amount=40,
        crit=False, missed=False, is_dot=False, hp_before=1000, hp_after=960, max_hp=1000, shielded=160,
    )
    line = battle_log._hit_line(hit, "А", "Б", "pvp")
    assert "200 урона" in line and "щит поглотил 160" in line
    dot = RenderedHit(
        source_id=1, target_id=2, source_side=0, target_side=1, label="яд", amount=0,
        crit=False, missed=False, is_dot=True, hp_before=1000, hp_after=1000, max_hp=1000, shielded=50,
        is_tick=True,
    )
    assert "щит поглотил 50" in battle_log._dot_line(dot, "Б")
