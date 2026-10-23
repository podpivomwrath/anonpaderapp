"""Паритет правил между движками: дуэль 1x1 и тиковый бой.

Аудит после патча 56 показал, что дуэльный движок реализует ход сам и поэтому
не получал ничего из resolve_tick: у Отравителя не работала половина пула, яд
шёл сквозь щиты, у Клинка теней молчала память между ходами. Общие правила
вынесены в game/combat/shared_rules.py; здесь проверяется, что оба движка их
действительно зовут и что дуэль не расходится с групповым боем.
"""

import asyncio
import random

from game.combat import balance_config as bc
from game.combat import shared_rules
from game.combat.duel_engine import DuelEngine
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    Effect,
    EffectKind,
)
from tests.conftest import NoCritRng, combatant


def poison(target, source_id: int, stacks: int = 3, value: float = 20.0, ticks: int = 3) -> Effect:
    effect = Effect(kind=EffectKind.DOT, value=value, remaining_ticks=ticks,
                    source_id=source_id, stacks=stacks)
    target.effects.append(effect)
    return effect


def duel_poison_damage(mods: dict, *, pool: int = 0, stacks: int = 3) -> int:
    """Один ход дуэли: жертва под ядом отравителя, возвращаем потерянное HP."""
    engine = DuelEngine(rng=random.Random(1))
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = dict(mods)
    victim = combatant(2, side=1, vitality=500)
    engine.start_duel(1, poisoner, victim)
    state = engine.duels[1]
    # ДоТ тикает в начале хода СВОЕЙ цели - убеждаемся, что ходит жертва
    if state.combatants[state.current_actor_id].id == poisoner.id:
        state.turn_number += 1
    actor = state.combatants[state.current_actor_id]
    if pool:
        actor.effects.append(Effect(kind=EffectKind.SHIELD_POOL, value=pool,
                                    remaining_ticks=5, source_id=actor.id))
    poison(actor, source_id=poisoner.id, stacks=stacks)
    before = actor.current_hp
    asyncio.run(engine._resolve_turn(state, DeclaredAction(type=ActionType.SKIP)))
    return before - actor.current_hp


def tick_poison_damage(mods: dict, *, pool: int = 0, stacks: int = 3) -> int:
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = dict(mods)
    victim = combatant(2, side=1, vitality=500)
    if pool:
        victim.effects.append(Effect(kind=EffectKind.SHIELD_POOL, value=pool,
                                     remaining_ticks=5, source_id=victim.id))
    poison(victim, source_id=poisoner.id, stacks=stacks)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(victim)
    state.tick_number = 1
    before = victim.current_hp
    resolve_tick(state, {}, NoCritRng())
    return before - victim.current_hp


# --- Урон ядом одинаков в обоих движках ---


def test_poison_damage_matches_between_engines() -> None:
    assert duel_poison_damage({}) == tick_poison_damage({})


def test_corroding_toxin_works_in_duel() -> None:
    plain = duel_poison_damage({})
    boosted = duel_poison_damage({"poison_damage_bonus": bc.POISONER_CORRODING_TOXIN_BONUS})
    assert boosted > plain
    assert boosted == tick_poison_damage({"poison_damage_bonus": bc.POISONER_CORRODING_TOXIN_BONUS})


def test_necrosis_works_in_duel() -> None:
    plain = duel_poison_damage({})
    boosted = duel_poison_damage({"poison_damage_per_stack": bc.POISONER_NECROSIS_PER_STACK})
    assert boosted > plain
    assert boosted == tick_poison_damage({"poison_damage_per_stack": bc.POISONER_NECROSIS_PER_STACK})


# --- Щиты держат яд в дуэли так же, как в групповом бою ---


def test_shield_pool_stops_poison_in_duel() -> None:
    assert duel_poison_damage({}, pool=1000) == 0
    assert tick_poison_damage({}, pool=1000) == 0


def test_toxicology_pierces_shield_pool_in_both_engines() -> None:
    """«Токсикология» обещает игроку проход мимо доли ЩИТА - без уточнения,
    какого именно, поэтому «Второе сердце» она пробивает наравне с однотиковым."""
    mods = {"poison_shield_pierce": bc.POISONER_TOXICOLOGY_SHIELD_PIERCE}
    in_duel = duel_poison_damage(mods, pool=1000)
    in_tick = tick_poison_damage(mods, pool=1000)
    assert in_duel > 0
    assert in_duel == in_tick


# --- Номер хода доезжает до правил ---


def test_duel_session_view_carries_turn_number() -> None:
    """Без этого `tick_number % N == 0` было бы истинно каждый ход дуэли."""
    engine = DuelEngine(rng=random.Random(1))
    engine.start_duel(1, combatant(1, side=0), combatant(2, side=1))
    state = engine.duels[1]
    state.turn_number = 7
    assert state.as_session_state().tick_number == 7


# --- Память Клинка теней ведётся и в дуэли ---


def test_bloodlust_arms_after_crit_in_duel() -> None:
    engine = DuelEngine(rng=NoCritRng())
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    # 100% шанс крита: крит случается ВНУТРИ хода, подставить флаг заранее
    # нельзя - начало хода его сбрасывает.
    blade.buff_modifiers = {
        "bloodlust_cooldown": float(bc.SHADOW_BLADE_BLOODLUST_COOLDOWN),
        "crit_chance_bonus": 1.0,
    }
    enemy = combatant(2, side=1, vitality=5000, agility=0)
    engine.start_duel(1, blade, enemy)
    state = engine.duels[1]
    if state.combatants[state.current_actor_id].id != blade.id:
        state.turn_number += 1  # пусть бьёт именно Клинок теней
    asyncio.run(engine._resolve_turn(
        state, DeclaredAction(type=ActionType.ATTACK, target_id=enemy.id)
    ))
    assert blade.crit_this_tick is True      # крит действительно случился
    assert blade.guaranteed_crit_next is True


def test_blocked_window_is_tracked_in_duel() -> None:
    """Окно «Возмездия» Стража должно двигаться каждый ход, иначе бафф в дуэли
    просто не накопит истории блоков."""
    engine = DuelEngine(rng=random.Random(1))
    guard = combatant(1, side=0, subclass_id="guardian")
    enemy = combatant(2, side=1)
    engine.start_duel(1, guard, enemy)
    state = engine.duels[1]
    asyncio.run(engine._resolve_turn(state, DeclaredAction(type=ActionType.SKIP)))
    assert len(guard.blocked_recent) == 1
    assert len(enemy.blocked_recent) == 1


# --- Мерж модификаторов: направление «выгодно игроку» ---


def test_interval_keys_merge_towards_lower_value() -> None:
    from game.content_loader import BuffDef
    from services.preset_service import resolve_buff_modifiers

    def buff(buff_id: str, **mods: float) -> BuffDef:
        return BuffDef(id=buff_id, name=buff_id, subclass="x", category="damage",
                       description="", stat_modifiers=mods, duration_ticks=1, implemented=True)

    catalog = {
        "slow": buff("slow", bloodlust_cooldown=8.0, damage_bonus=0.05),
        "fast": buff("fast", bloodlust_cooldown=4.0, damage_bonus=0.10),
    }
    merged = resolve_buff_modifiers(["slow", "fast"], catalog)
    assert merged["bloodlust_cooldown"] == 4.0   # кулдаун: меньше = лучше
    assert merged["damage_bonus"] == 0.10        # прибавка: больше = лучше


def test_lower_is_better_covers_cooldowns_and_intervals() -> None:
    assert shared_rules is not None  # модуль общих правил на месте
    from services.preset_service import is_lower_better

    assert is_lower_better("bloodlust_cooldown")
    assert is_lower_better("second_chance_interval")
    assert not is_lower_better("damage_bonus")
    assert not is_lower_better("ward_shield_bonus")


def test_block_reflection_works_in_duel() -> None:
    """«Отражение» Стража возвращает долю срезанного блоком урона и в дуэли:
    раньше правило жило только в резолвере.

    Полный блок - не пассивка: Страж тратит на «Глухую оборону» свой ход, и
    защита держится до начала его следующего хода, то есть как раз накрывает
    ответный удар противника."""
    class AlwaysBlockRng(NoCritRng):
        def random(self) -> float:
            return 0.0  # полный блок срабатывает

    engine = DuelEngine(rng=AlwaysBlockRng())
    attacker = combatant(1, side=0, vitality=500)
    guard = combatant(2, side=1, subclass_id="guardian", agility=0, vitality=500)
    guard.buff_modifiers = {
        "full_block_chance": 1.0,
        "block_reflect_pct": bc.GUARDIAN_REFLECTION_PCT,
    }
    engine.start_duel(1, attacker, guard)
    state = engine.duels[1]
    if state.combatants[state.current_actor_id].id != guard.id:
        state.turn_number += 1  # первым ходит Страж

    asyncio.run(engine._resolve_turn(
        state, DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block")
    ))
    assert guard.block_reduction == 1.0  # оборона поднята

    hp_before = attacker.current_hp
    asyncio.run(engine._resolve_turn(
        state, DeclaredAction(type=ActionType.ATTACK, target_id=guard.id)
    ))
    assert attacker.current_hp < hp_before  # часть удара вернулась атакующему


def test_shield_pool_absorbs_direct_hit_in_duel() -> None:
    """Проверка, что сведение щитов в общий модуль не потеряло поведение,
    которое чинил патч 52: «Второе сердце» работает и в дуэли."""
    engine = DuelEngine(rng=NoCritRng())
    attacker = combatant(1, side=0)
    target = combatant(2, side=1, agility=0, vitality=500)
    target.effects.append(Effect(kind=EffectKind.SHIELD_POOL, value=100000,
                                 remaining_ticks=5, source_id=target.id))
    engine.start_duel(1, attacker, target)
    state = engine.duels[1]
    if state.combatants[state.current_actor_id].id != attacker.id:
        state.turn_number += 1
    hp_before = target.current_hp
    asyncio.run(engine._resolve_turn(
        state, DeclaredAction(type=ActionType.ATTACK, target_id=target.id)
    ))
    assert target.current_hp == hp_before  # щит поглотил удар целиком


def _duel_hit_on(target, attacker, rng=None) -> None:
    """Один удар attacker по target в дуэли."""
    engine = DuelEngine(rng=rng or NoCritRng())
    engine.start_duel(1, attacker, target)
    state = engine.duels[1]
    if state.combatants[state.current_actor_id].id != attacker.id:
        state.turn_number += 1
    asyncio.run(engine._resolve_turn(
        state, DeclaredAction(type=ActionType.ATTACK, target_id=target.id)
    ))


def test_damage_cap_works_in_duel() -> None:
    """«Несокрушимый» (2026-10-22): в дуэли потолка урона за удар не было."""
    attacker = combatant(1, side=0, strength=5000)
    target = combatant(2, side=1, agility=0, vitality=500)
    target.apply_effect(EffectKind.DAMAGE_CAP, 0.05, 3, target.id)
    before = target.current_hp
    _duel_hit_on(target, attacker)
    assert before - target.current_hp == round(target.max_hp * 0.05)


def test_block_heal_works_in_duel() -> None:
    """«Глухая оборона» лечит за удар в стойку и в дуэли (2026-10-22)."""
    attacker = combatant(1, side=0)
    target = combatant(2, side=1, agility=0, vitality=500)
    target.apply_effect(EffectKind.BLOCK_STANCE, 1.0, 3, target.id)
    target.apply_effect(EffectKind.BLOCK_HEAL, 0.05, 3, target.id)
    target.current_hp = target.max_hp // 2
    before = target.current_hp
    _duel_hit_on(target, attacker)
    assert target.current_hp > before  # удар срезан стойкой, лечение пришло


def test_every_effect_the_tick_engine_reads_is_known_to_the_duel() -> None:
    """Сверка (2026-10-22): эффект, который читает тиковый бой, обязан читаться
    и в дуэли (сам движок, общие правила или навыки) - иначе он молча не
    работает в 1x1, как было с «Кровью за кровь», «Несокрушимым» и «Глухой
    обороной». Исключение - только с причиной."""
    import re
    from pathlib import Path

    combat = Path(__file__).resolve().parents[1] / "game" / "combat"

    def kinds(*names: str) -> set[str]:
        return {
            k for n in names
            for k in re.findall(r"EffectKind\.([A-Z_]+)", (combat / f"{n}.py").read_text(encoding="utf-8"))
        }

    exempt = {
        # В резолвере - только в списке «тикает сразу» (эликсиры); саму
        # невосприимчивость проверяет control.py, общий для обоих движков.
        "CONTROL_IMMUNE",
    }
    missing = kinds("resolver") - kinds("duel_engine", "shared_rules", "skills", "control") - exempt
    assert not missing, f"дуэль не знает эффектов: {sorted(missing)}"


def _capped_guardian():
    """Страж под «Несокрушимым»: удар не выше 5% его макс. HP."""
    g = combatant(2, side=1, subclass_id="guardian", vitality=200)
    g.effects.append(Effect(kind=EffectKind.DAMAGE_CAP, value=0.05, remaining_ticks=3, source_id=2))
    return g


def test_lifesteal_heals_from_damage_that_got_through() -> None:
    """2026-10-24, жалоба: Кровопуск по Стражу под «Несокрушимым» лечил от
    полного удара, а не от срезанного потолком. Оба движка."""
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    cap_pct = 0.05
    ratio = SUBCLASS_SKILL_DEFS["blood_knight_lifesteal_strike"].effect_value
    # Тиковый бой
    knight = combatant(1, side=0, level=60, subclass_id="blood_knight", strength=300)
    knight.current_hp = knight.max_hp // 4
    g = _capped_guardian()
    s = CombatSessionState(session_id=1, mode=CombatMode.DUEL)
    s.add(knight)
    s.add(g)
    before = knight.current_hp
    resolve_tick(s, {1: DeclaredAction(type=ActionType.SKILL, skill_id="blood_knight_lifesteal_strike",
                                       target_id=2)}, NoCritRng(1))
    dealt = round(g.max_hp * cap_pct)
    assert knight.current_hp - before <= round(dealt * ratio) + 1
    # Дуэль
    engine = DuelEngine(rng=NoCritRng(1))
    knight = combatant(1, side=0, level=60, subclass_id="blood_knight", strength=300)
    knight.current_hp = knight.max_hp // 4
    g = _capped_guardian()
    engine.start_duel(2, knight, g)
    state = engine.duels[2]
    if state.current_actor_id != knight.id:
        state.turn_number += 1
    before = knight.current_hp
    asyncio.run(engine._resolve_turn(state, DeclaredAction(
        type=ActionType.SKILL, skill_id="blood_knight_lifesteal_strike", target_id=2)))
    assert knight.current_hp - before <= round(dealt * ratio) + 1
