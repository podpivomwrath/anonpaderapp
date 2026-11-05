"""Руна «Ответный выпад» (2026-11-05): увернулся - удары следующего хода
сильнее и отмечены в логе; увороты подряд не складываются."""

import random

from game.combat import battle_log
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, Stats, build_combatant
from game.combat.skills import compute_hit


def _rogue(rune: float = 0.2):
    return build_combatant(id=1, side=0, kind="character", name="Разбойник", level=60,
                           stats=Stats(strength=60, agility=400, intellect=60, vitality=300, will=60),
                           primary_stat="agi", base_class="rogue",
                           buff_modifiers={"rune:riposte": rune} if rune else {})


def _mob():
    return build_combatant(id=2, side=1, kind="mob", name="Моб", level=60,
                           stats=Stats(strength=200, agility=10, intellect=10, vitality=5000, will=10),
                           primary_stat="str")


def test_bonus_only_after_dodge_and_flat() -> None:
    plain = compute_hit(_rogue(), _mob(), random.Random(5), label="бьёт")
    rogue = _rogue()
    rogue.dodged_last_tick = True
    boosted = compute_hit(rogue, _mob(), random.Random(5), label="бьёт")
    assert not plain.riposte and boosted.riposte
    assert boosted.amount == round(plain.amount * 1.2) or abs(boosted.amount - plain.amount * 1.2) <= 1
    without = _rogue(0.0)
    without.dodged_last_tick = True
    assert not compute_hit(without, _mob(), random.Random(5), label="бьёт").riposte


def test_marked_in_log_on_the_tick_after_a_dodge() -> None:
    seen = False
    for seed in range(200):
        s = CombatSessionState(session_id=seed, mode=CombatMode.PVE, is_raid=True)
        rogue, mob = _rogue(), _mob()
        s.add(rogue)
        s.add(mob)
        rng = random.Random(seed)
        for _ in range(6):
            prev = rogue.dodged_last_tick
            res = resolve_tick(s, {1: DeclaredAction(type=ActionType.ATTACK, target_id=2)}, rng)
            landed = any(h.source_id == 1 and not h.missed for h in res.hit_renders)
            marked = [h for h in res.hit_renders if h.riposte]
            assert bool(marked) == (prev and landed)
            if marked:
                seen = True
                assert "ответный выпад" in battle_log.render_tick(s, res, viewer_side=0)
            if res.finished:
                break
    assert seen
