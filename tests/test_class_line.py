"""Свои классовые механики под доской боя (2026-10-13, просьба игроков)."""

import random

from game.combat import battle_log
from game.combat.session import BURN_TAG, CombatMode, CombatSessionState, EffectKind
from game.combat.skills import compute_hit
from tests.conftest import combatant


def _session(owner_sub: str):
    owner = combatant(1, side=0, subclass_id=owner_sub)
    ally = combatant(2, side=0)
    mob = combatant(3, side=1, kind="mob")
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    for c in (owner, ally, mob):
        state.add(c)
    return state, owner, ally, mob


def test_no_subclass_or_nothing_hanging_gives_none() -> None:
    state, owner, _ally, _mob = _session("poisoner")
    assert battle_log.class_line(state.combatants, owner.id) is None


def test_each_subclass_sees_its_own_mechanic() -> None:
    cases = {
        "shadow_blade": (lambda o, a, m: m.apply_effect(EffectKind.MARK, 1.0, 3, o.id), "Метка добычи"),
        "poisoner": (lambda o, a, m: m.apply_effect(EffectKind.DOT, 5.0, 3, o.id), "Яд"),
        "elementalist": (lambda o, a, m: m.apply_effect(EffectKind.DOT, 5.0, 2, o.id, tag=BURN_TAG), "Горит"),
        "blood_knight": (lambda o, a, m: m.apply_effect(EffectKind.BLOOD_SEAL, 1.0, 3, o.id), "Кровавая печать"),
        "guardian": (lambda o, a, m: o.apply_effect(EffectKind.BLOCK_STANCE, 0.5, 2, o.id), "Глухая оборона"),
        "dark_mystic": (lambda o, a, m: a.apply_effect(EffectKind.SHIELD_POOL, 120.0, 3, o.id), "Оберег"),
    }
    for sub, (setup, word) in cases.items():
        state, owner, ally, mob = _session(sub)
        setup(owner, ally, mob)
        line = battle_log.class_line(state.combatants, owner.id)
        assert line and word in line, (sub, line)


def test_poisoner_does_not_see_someone_elses_poison() -> None:
    state, owner, ally, mob = _session("poisoner")
    mob.apply_effect(EffectKind.DOT, 5.0, 3, ally.id)  # яд союзника
    assert battle_log.class_line(state.combatants, owner.id) is None


def test_dodge_line_shows_mark_from_blade_hunger() -> None:
    """«Голод клинка»: уворот ставит Метку - строка уворота это показывает."""
    blade = combatant(1, side=0, subclass_id="shadow_blade", agility=200)
    blade.buff_modifiers = {"mark_on_dodge": 1.0}
    blade.second_chance_active = True  # гарантированный уворот
    mob = combatant(2, side=1, kind="mob")
    hit = compute_hit(mob, blade, random.Random(1), "бьёт")
    assert hit.missed and hit.marked == 1


def test_shield_lines_name_their_source() -> None:
    """Оберег мистика в логе - «Оберег», а не «Второе сердце»; эликсир и свой
    Оберег на одном бойце - два отдельных щита."""
    from game.combat.session import SECOND_HEART_TAG, WARD_TAG
    from game.combat.shared_rules import absorb_by_shields

    state, owner, _ally, _mob = _session("dark_mystic")
    owner.apply_effect(EffectKind.SHIELD_POOL, 100.0, 3, owner.id, tag=WARD_TAG)
    owner.apply_effect(EffectKind.SHIELD_POOL, 50.0, 3, owner.id, tag=SECOND_HEART_TAG)
    assert len(owner.effects_of(EffectKind.SHIELD_POOL)) == 2
    lines: list[str] = []
    absorb_by_shields(owner, 30, lines)
    assert "Оберег" in lines[0] and "Второе сердце" not in lines[0]
    line = battle_log.class_line(state.combatants, owner.id)
    assert "Оберег: ты - 70" in line


def test_last_breath_turns_shown_to_any_class() -> None:
    """«Последний вздох» действует 3 хода - остаток виден под доской боя."""
    state, owner, _ally, _mob = _session("poisoner")
    owner.subclass_id = None
    owner.apply_effect(EffectKind.LAST_BREATH, 1.0, 2, owner.id)
    assert "Последний вздох (ещё 2 х.)" in battle_log.class_line(state.combatants, owner.id)


def test_damage_flows_through_all_shields() -> None:
    """2026-10-13: урон идёт через все щиты по очереди (первым - истекающий
    раньше), пустые снимаются и не закрывают собой остальные."""
    from game.combat.session import SECOND_HEART_TAG, WARD_TAG
    from game.combat.shared_rules import absorb_by_shields

    _state, owner, _ally, _mob = _session("dark_mystic")
    owner.apply_effect(EffectKind.SHIELD_POOL, 50.0, 1, owner.id, tag=WARD_TAG)
    owner.apply_effect(EffectKind.SHIELD_POOL, 100.0, 3, owner.id, tag=SECOND_HEART_TAG)
    lines: list[str] = []
    assert absorb_by_shields(owner, 120, lines) == 0  # 50 Оберег + 70 Второе сердце
    assert "Оберег" in lines[0] and "Второе сердце" in lines[1]
    left = owner.effects_of(EffectKind.SHIELD_POOL)
    assert len(left) == 1 and left[0].value == 30  # пустой Оберег снят
    assert absorb_by_shields(owner, 50, []) == 20
    assert not owner.effects_of(EffectKind.SHIELD_POOL)
