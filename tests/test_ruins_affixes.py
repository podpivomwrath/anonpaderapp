"""Навыки мобов руин вместо надбавки уровня (2026-11-13, идея Есты, владелец)."""

import random

from game import ruins as rules
from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.ruins import BossRoom, RoomStage
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.economy import ruins_affix_config as rax
from game.economy import ruins_config as rc
from tests.conftest import combatant


def _stage(floor: int, room: str = rules.FIGHT, party: int = 1):
    layout = {**rules.generate(random.Random(3), floor), "floor": floor}
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    stage = RoomStage(22_000_000, layout, room, party)
    lines = stage.setup(state)
    foes = [c for c in state.combatants.values() if c.side == 1]
    return stage, foes, lines


def test_counts_and_tiers() -> None:
    assert [rax.count(f) for f in (1, 5, 6, 15, 16, 30, 31, 80)] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert [rax.tier(f) for f in (6, 10, 11, 16, 31)] == [1, 1, 2, 3, 6]
    # отражение: старт 20%, потолок 50% (владелец)
    reflect = rax.BY_ID["reflect"]
    assert reflect.value(1) == 0.20 and reflect.value(100) == 0.50
    for a in rax.AFFIXES:
        assert a.kind in __import__("game.combat.mob_abilities", fromlist=["KINDS"]).KINDS


def test_floor_affixes_are_stable_and_respect_min_floor() -> None:
    layout = rules.generate(random.Random(5), 20)
    assert rax.for_floor(layout) == rax.for_floor(dict(layout))
    for seed in range(50):
        early = rules.generate(random.Random(seed), 10)
        common, extra = rax.for_floor(early)
        assert "last_breath" not in common + extra
        assert len(common) == 1 and len(extra) == 1 and not set(common) & set(extra)


def test_level_is_cap_and_early_floors_have_no_skills() -> None:
    _, foes, lines = _stage(3)
    assert all(f.level == bc.MAX_LEVEL and f.mob_brain is None for f in foes)
    assert not any("Навыки" in line for line in lines)


def test_mobs_get_floor_skills_and_elite_one_more() -> None:
    stage, foes, lines = _stage(17, rules.ELITE, party=3)
    elite = next(f for f in foes if f.name == stage.elite_name)
    common = [f for f in foes if f is not elite]
    assert all(len(f.mob_brain.ability.traits) == 2 and f.silence_keeps_body for f in common)
    assert len(elite.mob_brain.ability.traits) == 3
    assert any(line.startswith("🧿 Навыки мобов этажа:") for line in lines)
    assert any(line.startswith(f"🧿 {stage.elite_name} ещё и:") for line in lines)


def test_unique_bosses_have_no_ruins_skills() -> None:
    layout = {**rules.generate(random.Random(3), 20), "floor": 20}
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    BossRoom(22_000_000, layout, rules.BOSS, 1, rng=random.Random(1)).setup(state)
    assert all(c.mob_brain is None for c in state.combatants.values() if c.side == 1)


def _reflect_fight(silenced: bool):
    _, foes, _ = _stage(31)
    mob = foes[0]
    mob.mob_brain.traits = {"reflect": mob.mob_brain.traits.get("reflect")
                            or [type(mob.mob_brain.ability.traits[0])(kind="reflect", value=0.5)]}
    mob.max_hp = mob.current_hp = 10**6
    if silenced:
        mob.apply_effect(EffectKind.SILENCE, 1.0, 3, 1)
    hero = combatant(1, side=0, strength=200, vitality=500)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    state.add(hero)
    state.add(mob)
    result = resolve_tick(state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=mob.id)}, random.Random(2))
    return result


def test_silence_keeps_body_skills_of_ruins_mobs() -> None:
    """Немота глушит ход (вампиризм, яд, ярость), но не тело: отражение
    работает (2026-11-13, владелец)."""
    for silenced in (False, True):
        result = _reflect_fight(silenced)
        assert any(h.label == "возвращает урон" for h in result.hit_renders), silenced


def test_floor_line_shows_skills_instead_of_level() -> None:
    from bot import ruins_texts

    layout = rules.generate(random.Random(1), 16)
    line = ruins_texts.floor_line(16, layout)
    assert line.startswith("🕳 Этаж 16 · навыки мобов: ") and "ур." not in line
    assert ruins_texts.floor_line(2, rules.generate(random.Random(1), 2)) == "🕳 Этаж 2"
    assert rc.mob_level(16) == bc.MAX_LEVEL
