"""Классовые испытания во всех боях (2026-10-24, владелец: «во все бои все
должно работать»): трекер ведёт каждого участника группового боя, рейда и
разлома, врагами считается вся другая сторона."""

from types import SimpleNamespace

from bot import trial_tracking
from game.combat.battle_report import BattleTracker
from game.combat.session import ActionType, DeclaredAction


def _hit(src, dst, crit=False, amount=10):
    return SimpleNamespace(source_id=src, target_id=dst, crit=crit, amount=amount, is_dot=False, missed=False)


def _result(hits, deaths=(), actions=None):
    return SimpleNamespace(hits=hits, deaths=list(deaths), actions=actions or {}, control_landed_by=set(),
                           hit_renders=[])


def test_tracker_counts_every_enemy_and_finisher() -> None:
    t = BattleTracker(1, None, 60, 100, 100, enemy_ids={7, 8})
    skill = DeclaredAction(type=ActionType.SKILL, skill_id="blood_knight_lifesteal_strike", target_id=8)
    t.update(_result([_hit(1, 7, crit=True), _hit(8, 1)]), 90)
    t.update(_result([_hit(1, 8, crit=True)], deaths=[8], actions={1: skill}), 90, died_ids={8})
    r = t.finalize(True)
    assert r.crits_dealt == 2 and r.consecutive_crits
    assert r.hits_taken == 1 and r.total_damage_taken == 10
    assert r.finisher_is_crit and r.finisher_skill_id == "blood_knight_lifesteal_strike"


def test_observe_keeps_one_tracker_per_participant() -> None:
    me = SimpleNamespace(id=1, side=0, current_hp=80, max_hp=100, level=50)
    ally = SimpleNamespace(id=2, side=0, current_hp=100, max_hp=100, level=50)
    mob = SimpleNamespace(id=9, side=1, current_hp=10, max_hp=100, level=55)
    combatants = {1: me, 2: ally, 9: mob}
    try:
        trial_tracking.observe(-77, combatants, _result([_hit(1, 9, crit=True), _hit(2, 9)]), [1, 2])
        trial_tracking.observe(-77, combatants, _result([_hit(9, 1)]), [1, 2])
        by = trial_tracking._trackers[-77]
        assert set(by) == {1, 2}
        assert by[1].report.crits_dealt == 1 and by[1].report.hits_taken == 1
        assert by[2].report.crits_dealt == 0 and by[2].report.mob_level == 55
    finally:
        trial_tracking.drop(-77)
    assert -77 not in trial_tracking._trackers
