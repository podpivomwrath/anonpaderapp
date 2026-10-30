"""Боевые руны (2026-10-31): общие правила shared_rules для тикового боя и
дуэли - спасения, вампиризм, шипы, «Злоба», яд, перезарядка навыков
подкласса, «Тяжёлый взгляд», «Глухой щит», ослабление в PvP."""

import random

from game.combat import shared_rules
from game.combat.session import CombatMode, CombatSessionState, Effect, EffectKind
from game.combat.skills import PendingHit, SkillContext, compute_hit
from game.economy import runes
from tests.conftest import NoCritRng, combatant


class AlwaysRng(random.Random):
    """Любой шанс срабатывает."""

    def random(self) -> float:
        return 0.0


def test_not_today_saves_once() -> None:
    c = combatant(1, 0)
    c.buff_modifiers["rune:not_today"] = 0.05
    c.current_hp = -5
    lines: list[str] = []
    shared_rules.rune_guard(c, lines, AlwaysRng())
    assert c.current_hp == 1 and lines
    c.current_hp = -5
    shared_rules.rune_guard(c, lines, AlwaysRng())
    assert c.current_hp == -5  # второй раз за бой - нет


def test_spare_breath_heals_below_30_once() -> None:
    c = combatant(1, 0)
    c.buff_modifiers["rune:spare_breath"] = 0.10
    c.current_hp = round(c.max_hp * 0.2)
    before = c.current_hp
    shared_rules.rune_guard(c, [])
    assert c.current_hp == before + round(c.max_hp * 0.10)
    c.current_hp = 1
    shared_rules.rune_guard(c, [])
    assert c.current_hp == 1


def test_on_hit_lifesteal_spite_thorns() -> None:
    a, t = combatant(1, 0), combatant(2, 1)
    a.buff_modifiers["rune:red_thirst"] = 0.03
    t.buff_modifiers["rune:thorn_plate"] = 0.08
    heals: list = []
    hit = PendingHit(source_id=1, target_id=2, amount=100)
    assert shared_rules.rune_on_hit(a, t, hit, heals) == 0.08
    assert t.hits_taken == 1
    assert heals and heals[0].of_hit is hit and heals[0].ratio == 0.03
    # Яд не считается ударом: ни вампиризма, ни счётчика.
    dot = PendingHit(source_id=1, target_id=2, amount=50, is_dot=True)
    assert shared_rules.rune_on_hit(a, t, dot, heals) == 0.0 and t.hits_taken == 1


def test_dot_runes_and_cuirass() -> None:
    src, tgt = combatant(1, 0), combatant(2, 1)
    effect = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=1, stacks=1)
    base = shared_rules.poison_tick_damage(effect, src, tgt)
    src.buff_modifiers["rune:acrid@poisoner_venom"] = 0.15
    tgt.buff_modifiers["rune:bitter_blood"] = 0.12
    assert shared_rules.poison_tick_damage(effect, src, tgt) == round(base * 1.15 * 0.88)
    # Уязвимость на цели слабеет от «Литой кирасы» и для яда.
    tgt.buff_modifiers.clear()
    src.buff_modifiers.clear()
    tgt.apply_effect(EffectKind.VULNERABILITY, 0.4, 2, 1, decays=False)
    vulnerable = shared_rules.poison_tick_damage(effect, src, tgt)
    tgt.buff_modifiers["rune:cast_cuirass"] = 0.5
    assert shared_rules.poison_tick_damage(effect, src, tgt) < vulnerable


def test_cold_count_works_for_subclass_skill_that_sets_cooldown_directly() -> None:
    actor = combatant(1, 0, subclass_id="shadow_blade")
    enemy = combatant(2, 1)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: actor, 2: enemy})
    actor.buff_modifiers["rune:cold_count@shadow_blade_marked_strike"] = 0.08
    ctx = SkillContext(session=session, actor=actor, action=None, rng=AlwaysRng())

    def handler(c):  # как навыки подклассов: перезарядка напрямую
        c.actor.cooldowns["shadow_blade_marked_strike"] = 2

    shared_rules.run_skill(handler, ctx, "shadow_blade_marked_strike")
    assert actor.cooldowns["shadow_blade_marked_strike"] == 0
    assert actor.current_skill is None


def test_heavy_gaze_cuts_field_mobs_once() -> None:
    player, mob = combatant(1, 0), combatant(2, 1, kind="mob")
    mob.field_mob = True
    player.buff_modifiers["rune:heavy_gaze"] = 0.06
    full = mob.max_hp
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, combatants={1: player, 2: mob})
    shared_rules.rune_gaze(session)
    shared_rules.rune_gaze(session)
    assert mob.max_hp == round(full * 0.94)


def test_deaf_shield_blocks_only_basic_attacks() -> None:
    a, t = combatant(1, 0), combatant(2, 1)
    t.buff_modifiers["rune:deaf_shield"] = 0.06
    blocked = compute_hit(a, t, AlwaysRng(), ignore_dodge=True)
    assert blocked.missed and blocked.amount == 0
    skill_hit = compute_hit(a, t, NoCritRng(), is_ability=True)
    assert not skill_hit.missed and skill_hit.amount > 0


def test_pvp_scaling_keeps_full_and_drops_pve_only() -> None:
    scaled = runes.pvp_scaled({"rune:press@warrior_cleave": 0.10, "rune:ricochet@warrior_cleave": 0.12,
                               "rune:cast_cuirass": 0.25}, pvp=True)
    assert scaled == {"rune:press@warrior_cleave": 0.05, "rune:cast_cuirass": 0.25}
