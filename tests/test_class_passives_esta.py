"""Вторые строки пассивок подклассов и путей (2026-11-15, предложения Есты,
числа владельца). Каждая проверка - одно свойство из passives_config."""

import random

from game.classes import blood_knight, dark_mystic
from game.combat import shared_rules
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.combat.skills import compute_hit
from game.economy import passives_config
from tests.conftest import combatant


def _session(*fighters, mode=CombatMode.PVE) -> CombatSessionState:
    session = CombatSessionState(session_id=1, mode=mode)
    for f in fighters:
        session.add(f)
    return session


def _attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def test_every_passive_line_has_mods() -> None:
    for key, passive in passives_config.PASSIVES.items():
        assert passive.lines and passive.mods, key


def test_warrior_path_stun_costs_the_next_turn() -> None:
    """Оглушение от удара ложится после действий хода - и сбивает следующий."""
    player = combatant(1, 0, strength=80, level=30)
    player.buff_modifiers["stun_on_hit_chance"] = 1.0
    mob = combatant(2, 1, kind="mob", level=30, vitality=400)
    session = _session(player, mob)
    session.tick_number = 1
    first = resolve_tick(session, {1: _attack(2)}, random.Random(3))
    assert any("оглушает" in line for line in first.lines)
    session.tick_number = 2
    second = resolve_tick(session, {1: _attack(2)}, random.Random(4))
    assert any(f"{mob.name} теряет ход" in line for line in second.lines)


def test_poisoner_hit_leaves_a_one_turn_debuff() -> None:
    player = combatant(1, 0, strength=60)
    player.buff_modifiers["debuff_on_hit_chance"] = 1.0
    mob = combatant(2, 1, kind="mob", vitality=400)
    session = _session(player, mob)
    session.tick_number = 1
    resolve_tick(session, {1: _attack(2)}, random.Random(5))
    kinds = {e.kind for e in mob.effects if e.source_id == 1}
    assert kinds & {EffectKind.WEAKEN, EffectKind.VULNERABILITY, EffectKind.HEAL_REDUCTION}


def test_mage_path_dispel_skips_shielded_targets() -> None:
    player = combatant(1, 0, strength=60)
    player.buff_modifiers["dispel_on_hit_chance"] = 1.0
    mob = combatant(2, 1, kind="mob", vitality=400)
    mob.apply_effect(EffectKind.DAMAGE_BUFF, 0.2, 3, 2)
    session = _session(player, mob)
    session.tick_number = 1
    resolve_tick(session, {1: _attack(2)}, random.Random(5))
    assert not mob.has_effect(EffectKind.DAMAGE_BUFF)

    shielded = combatant(3, 1, kind="mob", vitality=400)
    shielded.apply_effect(EffectKind.DAMAGE_BUFF, 0.2, 3, 3)
    shielded.apply_effect(EffectKind.SHIELD_POOL, 5, 3, 3)
    player2 = combatant(4, 0, strength=60)
    player2.buff_modifiers["dispel_on_hit_chance"] = 1.0
    session2 = _session(player2, shielded)
    session2.tick_number = 1
    resolve_tick(session2, {4: _attack(3)}, random.Random(5))
    assert shielded.has_effect(EffectKind.DAMAGE_BUFF)


def test_shadow_blade_pierce_only_against_players() -> None:
    def hit(pierce: float, kind: str) -> int:
        actor = combatant(1, 0, strength=100, level=60)
        actor.buff_modifiers["pvp_pierce_chance"] = pierce
        target = combatant(2, 1, kind=kind, vitality=300, level=60)
        return compute_hit(actor, target, random.Random(9), multiplier=1.0, force_crit=False).amount

    assert hit(1.0, "character") > hit(0.0, "character") * 1.2
    assert hit(1.0, "mob") == hit(0.0, "mob")


def test_agility_dodge_share() -> None:
    def dodge_rate(share: float, is_ability: bool, ratio: float = 0.0) -> float:
        rng = random.Random(11)
        missed = 0
        for _ in range(4000):
            actor = combatant(1, 0, strength=50)
            target = combatant(2, 1, agility=250)
            target.buff_modifiers["agi_dodge_share"] = share
            if ratio:
                target.buff_modifiers["ability_dodge_ratio"] = ratio
            missed += compute_hit(actor, target, rng, is_ability=is_ability).missed
        return missed / 4000

    base = dodge_rate(0.0, False)
    half = dodge_rate(0.5, False)
    # 250 Ловкости по кривой Воли - 22.5%, половина - ~11 п.п.
    assert 0.08 < half - base < 0.14
    assert dodge_rate(0.5, True, ratio=0.75) > dodge_rate(0.5, True) * 2


def test_blood_knight_resists_heal_reduction() -> None:
    knight = combatant(1, 0)
    knight.apply_effect(EffectKind.HEAL_REDUCTION, 0.4, 2, 9)
    assert knight.heal_reduction() == 0.4
    knight.buff_modifiers["heal_reduction_resist"] = 0.25
    assert abs(knight.heal_reduction() - 0.3) < 1e-9


def test_dark_mystic_receives_more_healing() -> None:
    mystic = combatant(1, 0)
    assert shared_rules.recovered(mystic, 100) == 100
    mystic.buff_modifiers["heal_received_bonus"] = 0.25
    assert shared_rules.recovered(mystic, 100) == 125


def test_dark_mystic_solo_heal_not_weaker() -> None:
    from types import SimpleNamespace

    mystic = combatant(1, 0)
    ctx = SimpleNamespace(actor=mystic, session=_session(mystic))
    assert dark_mystic._solo_heal_penalty(ctx) < 1.0
    mystic.buff_modifiers["no_solo_heal_penalty"] = 1.0
    assert dark_mystic._solo_heal_penalty(ctx) == 1.0


def test_chain_lightning_hits_one_more_at_80_percent() -> None:
    mage = combatant(1, 0, intellect=100, level=60)
    mage.buff_modifiers.update(passives_config.PASSIVES["elementalist"].mods)
    mobs = [combatant(10 + i, 1, kind="mob", level=60, vitality=2000) for i in range(5)]
    session = _session(mage, *mobs)
    session.tick_number = 1
    result = resolve_tick(session, {1: DeclaredAction(type=ActionType.SKILL, skill_id="elementalist_lightning",
                                                      target_id=10)}, random.Random(2))
    chain = [h for h in result.hits if h.source_id == 1 and h.skill_id == "elementalist_lightning"]
    assert len(chain) == 4  # цель и ещё трое (база 2 + пассивка 1)


def test_guardian_takes_a_basic_attack_in_pvp() -> None:
    enemy = combatant(1, 0, strength=60)
    ally = combatant(2, 1)
    guard = combatant(3, 1)
    guard.buff_modifiers["pvp_taunt_chance"] = 1.0
    session = _session(enemy, ally, guard, mode=CombatMode.PVP_GROUP)
    session.tick_number = 1
    result = resolve_tick(session, {1: _attack(2)}, random.Random(1))
    assert all(h.target_id == 3 for h in result.hits if h.source_id == 1)


def test_guardian_defense_can_last_longer() -> None:
    from types import SimpleNamespace

    guard = combatant(1, 0)
    guard.buff_modifiers["defense_extend_chance"] = 1.0
    guard.apply_effect(EffectKind.BLOCK_STANCE, 0.35, 2, 1)
    effect = guard.effects[-1]
    ctx = SimpleNamespace(rng=random.Random(1), lines=[])
    shared_rules._passive_extend(guard, "guardian_block", [effect], ctx)
    assert effect.remaining_ticks == 3
    shared_rules._passive_extend(guard, "warrior_cleave", [effect], ctx)
    assert effect.remaining_ticks == 3


def test_blood_knight_feeds_on_an_ally_seal() -> None:
    from types import SimpleNamespace

    from game.combat.skills import PendingHit

    def heal(any_seal: bool) -> int:
        knight = combatant(1, 0)
        ally = combatant(2, 0)
        mob = combatant(3, 1, kind="mob")
        if any_seal:
            knight.buff_modifiers["any_seal_lifesteal"] = 1.0
        mob.apply_effect(EffectKind.BLOOD_SEAL, 2.0, 3, ally.id)
        ctx = SimpleNamespace(actor=knight, session=_session(knight, ally, mob), heals=[])
        blood_knight._lifesteal_heal(ctx, PendingHit(source_id=1, target_id=3, amount=100), 0.2)
        return ctx.heals[0].amount

    assert heal(True) > heal(False)
