"""Ультимативные руны (2026-11-05, владелец: высоким тирам - сильные
эффекты): Свежие силы, Каменная воля, За своих, Счёт до четырёх,
Последнее слово, Ещё раз, Без передышки."""

import random

from game.combat import control, shared_rules
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.combat.skills import SkillContext, compute_hit
from game.economy import runes_config as rc
from tests.conftest import NoCritRng, combatant


class AlwaysRng(random.Random):
    def random(self) -> float:
        return 0.0


class NeverRng(random.Random):
    def random(self) -> float:
        return 0.999


def test_catalog_tiers() -> None:
    by = rc.BY_ID
    assert by["monolith_mark"].rarity == "common" and by["loose_tongue"].rarity == "common"
    assert {r: by[r].rarity for r in ("second_wind", "stone_will", "for_ours")} == dict.fromkeys(
        ("second_wind", "stone_will", "for_ours"), "epic")
    assert {r: by[r].rarity for r in ("heavy_swing", "last_word", "once_more", "no_rest")} == dict.fromkeys(
        ("heavy_swing", "last_word", "once_more", "no_rest"), "mythic")
    assert by["once_more"].pvp == "none" and by["no_rest"].pvp == "none"
    names = [r.name for r in rc.RUNES]
    assert len(names) == len(set(names))


def test_second_wind_resets_cooldowns_once() -> None:
    c = combatant(1, 0)
    c.buff_modifiers["rune:second_wind"] = 0.25
    c.cooldowns = {"a": 3, "b": 1}
    c.current_hp = round(c.max_hp * 0.5)
    shared_rules.rune_guard(c, [])
    assert c.cooldowns == {"a": 3, "b": 1}, "выше порога - нет"
    c.current_hp = round(c.max_hp * 0.2)
    lines: list[str] = []
    shared_rules.rune_guard(c, lines)
    assert c.cooldowns == {"a": 0, "b": 0} and any("Свежие силы" in x for x in lines)
    c.cooldowns = {"a": 3}
    shared_rules.rune_guard(c, [])
    assert c.cooldowns == {"a": 3}, "раз за бой"


def test_stone_will_shrugs_only_the_first_control() -> None:
    class WillRng(random.Random):
        """Резист воли не проходит, руна - проходит."""
        calls = 0

        def random(self) -> float:
            self.calls += 1
            return 0.999 if self.calls % 2 else 0.0

    target = combatant(2, 1)
    target.buff_modifiers["rune:stone_will"] = 0.5
    first = control.try_apply_control(target, 1, 9, WillRng(), pvp=False)
    assert not first.applied and first.resisted
    second = control.try_apply_control(target, 1, 9, NeverRng(), pvp=False)
    assert second.applied, "попытка руны одна за бой"
    plain = combatant(3, 1)
    assert control.try_apply_control(plain, 1, 9, NeverRng(), pvp=False).applied


def test_for_ours_counts_fallen_allies_up_to_three() -> None:
    a, ally, enemy = combatant(1, 0), combatant(2, 0), combatant(3, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: a, 2: ally, 3: enemy})
    a.buff_modifiers["rune:for_ours"] = 0.15
    base = compute_hit(a, enemy, NoCritRng(), label="бьёт").amount
    ally.current_hp = 0
    shared_rules.rune_after_deaths(session, [2], [], [], NeverRng())
    assert a.allies_fallen == 1
    boosted = compute_hit(a, enemy, NoCritRng(), label="бьёт").amount
    assert abs(boosted - base * 1.15) <= 1
    a.allies_fallen = 7
    capped = compute_hit(a, enemy, NoCritRng(), label="бьёт").amount
    assert abs(capped - base * 1.45) <= 1


def test_heavy_swing_every_fourth_hit_marked() -> None:
    a, enemy = combatant(1, 0), combatant(2, 1)
    a.buff_modifiers["rune:heavy_swing"] = 1.0
    hits = [compute_hit(a, enemy, NoCritRng(), label="бьёт") for _ in range(8)]
    landed = [h for h in hits if not h.missed]
    assert [h.heavy for h in landed][3] and [h.heavy for h in landed].count(True) == len(landed) // 4
    plain = [h.amount for h in landed if not h.heavy]
    heavy = [h.amount for h in landed if h.heavy]
    assert abs(heavy[0] - plain[0] * 2) <= 1


def test_last_word_hits_all_enemies_on_death() -> None:
    hero, m1, m2 = combatant(1, 0), combatant(2, 1), combatant(3, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: hero, 2: m1, 3: m2})
    hero.buff_modifiers["rune:last_word"] = 0.30
    before = {2: m1.current_hp, 3: m2.current_hp}
    hero.current_hp = 0
    lines: list[str] = []
    shared_rules.rune_last_word(session, {1, 2, 3}, lines)
    hit = round(hero.max_hp * 0.30)
    assert before[2] - m1.current_hp == min(hit, before[2]) and before[3] - m2.current_hp == min(hit, before[3])
    assert any("Последнее слово" in x for x in lines)
    shared_rules.rune_last_word(session, {1, 2, 3}, lines)
    assert before[2] - m1.current_hp == min(hit, before[2]), "раз за бой"


def test_once_more_reruns_half_without_new_cost() -> None:
    actor, enemy = combatant(1, 0), combatant(2, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: actor, 2: enemy})
    actor.buff_modifiers["rune:once_more@x"] = 0.10
    ctx = SkillContext(session=session, actor=actor, action=None, rng=AlwaysRng())
    hp = actor.current_hp

    def handler(c):
        c.actor.current_hp = c.actor.current_hp - 10  # цена навыка здоровьем
        c.actor.cooldowns["x"] = 3
        c.hits.append(compute_hit(c.actor, enemy, NoCritRng(), label="бьёт"))

    shared_rules.run_skill(handler, ctx, "x")
    landed = [h for h in ctx.hits if not h.missed]
    assert len(ctx.hits) == 2
    if len(landed) == 2:
        assert abs(landed[1].amount - landed[0].amount * 0.5) <= 1
    assert actor.cooldowns["x"] == 3 and actor.current_hp == hp - 10
    assert not actor.rune_half and actor.current_skill is None


def test_no_rest_resets_cooldown_of_the_killing_skill() -> None:
    actor, enemy = combatant(1, 0), combatant(2, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: actor, 2: enemy})
    actor.buff_modifiers["rune:no_rest@x"] = 0.5
    actor.cooldowns = {"x": 3, "y": 2}
    hit = compute_hit(actor, enemy, NoCritRng(), label="бьёт")
    hit.skill_id, hit.missed = "x", False
    enemy.current_hp = 0
    lines: list[str] = []
    shared_rules.rune_after_deaths(session, [2], [hit], lines, AlwaysRng())
    assert actor.cooldowns == {"x": 0, "y": 2} and any("Без передышки" in x for x in lines)


def test_last_word_in_a_real_tick() -> None:
    """Через резолвер: павший от моба бьёт словом, мобы от слова тоже в смертях хода."""
    hero, mob = combatant(1, 0), combatant(2, 1)
    hero.kind, mob.kind = "character", "mob"
    hero.buff_modifiers["rune:last_word"] = 0.30
    hero.current_hp = 1
    mob.current_hp = round(hero.max_hp * 0.30) - 1
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: hero, 2: mob})
    for seed in range(50):
        result = resolve_tick(session, {1: DeclaredAction(type=ActionType.SKIP)}, random.Random(seed))
        if not hero.alive:
            assert 2 in result.deaths and 1 in result.deaths
            return
    raise AssertionError("моб так и не ударил")


def test_event_runes_leave_a_log_line() -> None:
    """2026-11-05, владелец: руны-события видны в логе - «Холодный счёт»,
    «Короткий взмах», «Каменная воля» (а не просто «сопротивляется»)."""
    from game.combat import combat_flavor

    actor, enemy = combatant(1, 0), combatant(2, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: actor, 2: enemy})

    def handler(c):
        c.actor.cooldowns["x"] = 3

    for rune, word in (("cold_count", "Холодный счёт"), ("short_swing", "Короткий взмах")):
        actor.buff_modifiers = {f"rune:{rune}@x": 0.5}
        actor.cooldowns = {}
        ctx = SkillContext(session=session, actor=actor, action=None, rng=AlwaysRng())
        shared_rules.run_skill(handler, ctx, "x")
        assert any(word in x for x in ctx.lines), rune
    assert "Каменная воля" in combat_flavor.control_resisted_line("Страж", "stone_will")
    assert combat_flavor.control_resisted_line("Страж") == "Страж сопротивляется контролю."
