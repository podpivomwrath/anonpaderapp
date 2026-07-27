"""Патч 16: лавка эликсиров и зелий — контент, сервис, боевые механики."""

import random

import pytest
from sqlalchemy import select

from game.combat import control
from game.combat import elixir_effects
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.combat.skills import compute_hit
from game.content_loader import load_elixirs
from game.economy import elixir_config as ec
from models import CharacterConsumable
from services import elixir_service, wallet_service
from services.wallet_service import NotEnoughCurrency
from tests.conftest import NoCritRng, combatant


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def skip(target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKIP, target_id=target_id)


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


# --- Контент ---


def test_elixir_content_loads_ten_entries_matching_prices() -> None:
    defs = load_elixirs()
    assert len(defs) == 10
    assert set(defs) == set(ec.ELIXIR_PRICES)
    heal_ids = {eid for eid, d in defs.items() if d.category == "heal"}
    assert heal_ids == {"heal_small", "heal_medium", "heal_large"}


# --- services/elixir_service.py ---


async def test_buy_charges_gold_and_stacks(db_session, make_character) -> None:
    character = await make_character(farm=1000)
    await elixir_service.buy(db_session, character, "heal_small")
    await elixir_service.buy(db_session, character, "heal_small")
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 1000 - 2 * ec.ELIXIR_PRICES["heal_small"]
    row = await db_session.scalar(
        select(CharacterConsumable).where(
            CharacterConsumable.character_id == character.id,
            CharacterConsumable.elixir_id == "heal_small",
        )
    )
    assert row.count == 2


async def test_buy_without_gold_raises(db_session, make_character) -> None:
    character = await make_character(farm=0)
    with pytest.raises(NotEnoughCurrency):
        await elixir_service.buy(db_session, character, "last_breath")


async def test_get_stock_only_positive_counts(db_session, make_character) -> None:
    character = await make_character(farm=1000)
    await elixir_service.buy(db_session, character, "heal_small")
    stock = await elixir_service.get_stock(db_session, character.id)
    assert [d.id for d, _ in stock] == ["heal_small"]


async def test_consume_decrements_and_reports_empty(db_session, make_character) -> None:
    character = await make_character(farm=1000)
    await elixir_service.buy(db_session, character, "heal_small")
    assert await elixir_service.consume(db_session, character.id, "heal_small") is True
    assert await elixir_service.consume(db_session, character.id, "heal_small") is False


# --- Лечебные зелья: тратят ход (game/combat/resolver.py::ActionType.ITEM) ---


def test_heal_item_consumes_turn_and_heals_pct_max_hp() -> None:
    rng = NoCritRng()

    p_skip = combatant(1, side=0)
    p_skip.current_hp = 1
    resolve_tick(make_session(p_skip, combatant(2, side=1, kind="mob")), {1: skip(2)}, rng)
    hp_after_skip = p_skip.current_hp

    p_heal = combatant(3, side=0)
    p_heal.current_hp = 1
    resolve_tick(
        make_session(p_heal, combatant(4, side=1, kind="mob")),
        {3: DeclaredAction(type=ActionType.ITEM, item_id="heal_medium", target_id=3)},
        rng,
    )
    expected_heal = round(p_heal.max_hp * ec.HEAL_PCT["heal_medium"])
    assert p_heal.current_hp == min(hp_after_skip + expected_heal, p_heal.max_hp)


# --- 🔥 Пепельная лихорадка ---


def test_ashen_fever_escalates_and_self_damages_each_turn() -> None:
    rng = NoCritRng()
    player = combatant(1, side=0, strength=50, vitality=500)
    mob = combatant(2, side=1, kind="mob", strength=1, vitality=5000)
    session = make_session(player, mob)
    elixir_effects.apply_combat_elixir(player, "ashen_fever")
    assert player.effect_total(EffectKind.ASHEN_FEVER) == pytest.approx(ec.ASHEN_FEVER_DAMAGE_BONUS_STEP)

    hp_before = player.current_hp
    resolve_tick(session, {1: attack(2)}, rng)
    expected_self_dmg = max(round(player.max_hp * ec.ASHEN_FEVER_SELF_DAMAGE_PCT_MAX_HP), 1)
    assert player.current_hp <= hp_before - expected_self_dmg  # самоурон применился (+ возможно урон моба)
    assert player.effect_total(EffectKind.ASHEN_FEVER) == pytest.approx(2 * ec.ASHEN_FEVER_DAMAGE_BONUS_STEP)

    resolve_tick(session, {1: attack(2)}, rng)
    assert player.effect_total(EffectKind.ASHEN_FEVER) == pytest.approx(3 * ec.ASHEN_FEVER_DAMAGE_BONUS_STEP)

    resolve_tick(session, {1: attack(2)}, rng)
    assert player.effect_total(EffectKind.ASHEN_FEVER) == 0.0  # истёк после 3 ходов


def test_ashen_fever_boosts_outgoing_damage() -> None:
    rng = NoCritRng()
    attacker = combatant(1, side=0)
    target = combatant(2, side=1, kind="mob")
    baseline = compute_hit(attacker, target, rng)
    elixir_effects.apply_combat_elixir(attacker, "ashen_fever")
    boosted = compute_hit(attacker, target, rng)
    assert boosted.amount > baseline.amount


# --- 💀 Последний вздох ---


def test_last_breath_saves_from_lethal_damage_once() -> None:
    rng = NoCritRng()
    player = combatant(1, side=0, vitality=15)
    mob = combatant(2, side=1, kind="mob", strength=99999, level=60)
    session = make_session(player, mob)
    elixir_effects.apply_combat_elixir(player, "last_breath")

    resolve_tick(session, {1: skip(2)}, rng)
    assert player.current_hp == 1
    assert not player.has_effect(EffectKind.LAST_BREATH)  # разовое — снялось


# --- 🩸 Кровь за кровь ---


def test_blood_for_blood_reflects_damage_to_attacker() -> None:
    rng = NoCritRng()
    player = combatant(1, side=0)
    mob = combatant(2, side=1, kind="mob", vitality=5000)
    session = make_session(player, mob)
    elixir_effects.apply_combat_elixir(player, "blood_for_blood")
    mob_hp_before = mob.current_hp

    resolve_tick(session, {1: skip(2)}, rng)  # игрок не атакует — урон моба идёт первым
    assert mob.current_hp < mob_hp_before


# --- 🧿 Ясность крови ---


def test_blood_clarity_grants_control_immunity_in_pve() -> None:
    player = combatant(1, side=0)
    elixir_effects.apply_combat_elixir(player, "blood_clarity")
    result = control.try_apply_control(player, base_duration=2, source_id=99, rng=random.Random(1), pvp=False)
    assert result.applied is False
    assert result.immune is True


def test_blood_clarity_grants_control_immunity_in_pvp() -> None:
    player = combatant(1, side=0)
    elixir_effects.apply_combat_elixir(player, "blood_clarity")
    result = control.try_apply_control(player, base_duration=2, source_id=99, rng=random.Random(1), pvp=True)
    assert result.applied is False
    assert result.immune is True


# --- 🛡️ Второе сердце ---


def test_second_heart_absorbs_then_converts_remainder_to_heal() -> None:
    rng = NoCritRng()
    player = combatant(1, side=0, vitality=200)
    player.current_hp = player.max_hp - 200  # недобит, чтобы увидеть лечение
    mob = combatant(2, side=1, kind="mob", strength=1)  # слабые удары — щит не пробьётся
    session = make_session(player, mob)
    elixir_effects.apply_combat_elixir(player, "second_heart")
    hp_after_elixir = player.current_hp

    for _ in range(ec.SECOND_HEART_DURATION):
        resolve_tick(session, {1: skip(2)}, rng)

    assert player.current_hp > hp_after_elixir  # остаток щита обратился в лечение
    assert not player.effects_of(EffectKind.SHIELD_POOL)  # эффект закрылся


# --- 🌫️ Пепельный морок ---


class _AlwaysDodgeRng(random.Random):
    def random(self) -> float:
        return 0.0


def test_ashen_haze_grants_dodge_chance() -> None:
    player = combatant(1, side=0)
    mob = combatant(2, side=1, kind="mob")
    elixir_effects.apply_combat_elixir(player, "ashen_haze")
    assert player.effect_total(EffectKind.DODGE) == pytest.approx(ec.ASHEN_HAZE_DODGE_CHANCE)
    hit = compute_hit(mob, player, _AlwaysDodgeRng())
    assert hit.missed is True


# --- ⚡ Осколочная кровь ---


def test_shard_blood_adds_flat_damage_per_hit() -> None:
    rng = NoCritRng()
    player = combatant(1, side=0, level=20)
    mob = combatant(2, side=1, kind="mob", vitality=5000)
    baseline = compute_hit(player, mob, rng)
    elixir_effects.apply_combat_elixir(player, "shard_blood")
    boosted = compute_hit(player, mob, rng)
    expected_bonus = round(player.level * ec.SHARD_BLOOD_DAMAGE_PER_LEVEL)
    assert boosted.amount == baseline.amount + expected_bonus


# --- Лимит эликсиров за бой (счётчик на CombatantState) ---


def test_combat_elixirs_used_counter_starts_at_zero() -> None:
    player = combatant(1, side=0)
    assert player.combat_elixirs_used == 0
