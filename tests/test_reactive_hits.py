"""Ответные удары рун и отражений (шипы, «Обратная молитва») боссы и мобы
не отражают и на них не отвечают (владелец, 2026-11-07)."""

import random
from types import SimpleNamespace

from game.combat import resolver
from game.combat.session import CombatMode, CombatSessionState, EffectKind
from game.combat.skills import PendingHit
from tests.conftest import combatant


def _apply(hit):
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    state.add(combatant(1, side=0))
    boss = combatant(2, side=1)
    state.add(boss)
    boss.apply_effect(EffectKind.BLOOD_REFLECT, 0.5, 2, boss.id)
    ctx = SimpleNamespace(lines=[])
    return resolver._apply_phase(state, [hit], [], ctx, random.Random(1), {}, {}, resolver.TickResult())


def test_boss_reflect_skips_rune_hits() -> None:
    hit = PendingHit(source_id=1, target_id=2, amount=100, label="обратная молитва", reactive=True)
    assert _apply(hit) == []


def test_boss_reflect_still_answers_a_normal_hit() -> None:
    (back,) = _apply(PendingHit(source_id=1, target_id=2, amount=100, label="бьёт"))
    assert back.reactive  # и сам ответ дальше не отражается


def test_herald_ignores_rune_hits() -> None:
    import inspect

    from game.combat import ruins

    assert "reactive" in inspect.getsource(ruins)
