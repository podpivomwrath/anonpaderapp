"""Сопротивления (2026-11-02, репорт 283): стойкость к крит-урону, меткость,
стойкость к ядам. Источники - Выносливость (только криты, только у игроков),
руны героя, кованые вещи, Перстень Несгоревшего. Частоты крита и уворота
проверяются на большой выборке."""

import random

import pytest

from game.combat import shared_rules, stat_model
from game.combat.session import Effect, EffectKind
from game.combat.skills import compute_hit
from game.economy import resists
from game.economy import runes_config as rc
from models import Item
from services import preset_service, resist_service
from tests.conftest import combatant

N = 40_000


def _crit_rate(actor, target, seed=1) -> float:
    rng = random.Random(seed)
    crits = 0
    for _ in range(N):
        actor.crit_this_tick = False
        compute_hit(actor, target, rng, ignore_dodge=True)
        crits += actor.crit_this_tick
    return crits / N


def _dodge_rate(actor, target, seed=2) -> float:
    rng = random.Random(seed)
    missed = 0
    for _ in range(N):
        target.second_chance_active = False
        missed += compute_hit(actor, target, rng).missed
    return missed / N


def _crit_hit(actor, target) -> int:
    target.current_hp = target.max_hp
    return compute_hit(actor, target, random.Random(3), force_crit=True, ignore_dodge=True).amount


def test_crit_resist_cuts_crit_damage_not_chance() -> None:
    """Владелец (2026-11-02): стойкость режет прибавку крита, 100% - крит
    бьёт как обычный удар. Шанс крита не трогает."""
    rogue = combatant(1, 0, agility=200)
    mob = combatant(2, 1, kind="mob", vitality=400)
    mob.buff_modifiers["resist_crit"] = 1.0
    plain = _crit_hit(rogue, mob)            # крит без прибавки = обычный удар
    mob.buff_modifiers["resist_crit"] = 0.0
    full = _crit_hit(rogue, mob)             # Выносливость моба не в счёт
    mult = full / plain
    assert mult > 1.3
    mob.buff_modifiers["resist_crit"] = 0.2
    assert _crit_hit(rogue, mob) == pytest.approx(plain * (1 + (mult - 1) * 0.8), abs=2)
    mob.buff_modifiers["resist_crit"] = 5.0  # больше 100% - не лечит и не ниже обычного
    assert _crit_hit(rogue, mob) == plain
    # У игрока сверху - Выносливость.
    player = combatant(3, 1, vitality=400)
    vit = stat_model.ACTIVE.crit_resist(player.stats)
    assert vit == pytest.approx(0.10)
    player.buff_modifiers["resist_crit"] = 1.0
    p_plain = _crit_hit(rogue, player)
    player.buff_modifiers["resist_crit"] = 0.0
    assert _crit_hit(rogue, player) == pytest.approx(p_plain * (1 + (mult - 1) * (1 - vit)), abs=2)
    # Частота крита прежняя.
    player.buff_modifiers["resist_crit"] = 0.3
    base = stat_model.ACTIVE.crit_chance(rogue.stats)
    assert _crit_rate(rogue, player) == pytest.approx(base, abs=0.01)


def test_accuracy_cuts_dodge_and_floors_at_zero() -> None:
    attacker = combatant(1, 0)
    target = combatant(2, 1, will=250)
    target.buff_modifiers["dodge_bonus"] = 0.2
    base = _dodge_rate(attacker, target)
    attacker.buff_modifiers["accuracy"] = 0.15
    assert _dodge_rate(attacker, target) == pytest.approx(base * 0.85, abs=0.012)  # процент, не пункты
    attacker.buff_modifiers["accuracy"] = 3.0
    assert _dodge_rate(attacker, target) == 0.0


def test_dot_resist_with_floor() -> None:
    src, tgt = combatant(1, 0), combatant(2, 1)
    effect = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=1, stacks=1)
    base = shared_rules.poison_tick_damage(effect, src, tgt)
    tgt.buff_modifiers["resist_dot"] = 0.27
    assert shared_rules.poison_tick_damage(effect, src, tgt) == round(base * 0.73)
    tgt.buff_modifiers["resist_dot"] = 9.0
    assert shared_rules.poison_tick_damage(effect, src, tgt) == round(base * 0.1)


def test_item_value_and_lines() -> None:
    assert resists.item_value(120) == pytest.approx(0.10)
    assert resists.item_value(80) == pytest.approx(0.10 * 80 / 120)
    assert resists.item_value(None) == pytest.approx(0.10 * 100 / 120)
    item = Item(name="x", slot="weapon", craft_resist="crit", craft_efficiency=120)
    assert resist_service.item_line(item) == "крит-урон по тебе ниже на 10%"
    item.craft_resist, item.craft_efficiency = "dot", 90
    assert resist_service.item_line(item) == "яд и горение по тебе слабее на 7.5%"
    item.craft_resist = None
    assert resist_service.item_line(item) is None


def test_soft_cap() -> None:
    # Владелец (2026-11-02): до 15% полностью, сверху вполовину, не выше 30%.
    assert resists.capped(0.07) == pytest.approx(0.07)
    assert resists.capped(0.15) == pytest.approx(0.15)
    assert resists.capped(0.25) == pytest.approx(0.20)
    assert resists.capped(0.38) == pytest.approx(0.265)
    assert resists.capped(0.45) == pytest.approx(0.30)
    assert resists.capped(5.0) == pytest.approx(0.30)


async def test_stack_of_items_hits_cap(db_session, make_character) -> None:
    c = await make_character()
    c.resist_ring = True
    for slot in ("weapon", "helmet", "armor", "legs", "boots"):
        await _equip(db_session, c.id, Item(name=slot, slot=slot, craft_spec="tank", craft_resist="dot",
                                            craft_efficiency=120, base_stats={}))
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods["resist_dot"] == pytest.approx(resists.HARD_CAP)
    assert mods["resist_crit"] == pytest.approx(0.15)  # один перстень - полностью


def test_roll_spreads_evenly() -> None:
    rng = random.Random(5)
    counts = {k: 0 for k in resists.KINDS}
    for _ in range(30_000):
        counts[resists.roll(rng)] += 1
    assert all(abs(n / 30_000 - 1 / 3) < 0.015 for n in counts.values())


def test_hero_runes_full_in_pvp() -> None:
    for rune_id in ("tempered", "true_eye"):
        rune = rc.BY_ID[rune_id]
        assert rune.kind == rc.HERO and rune.value == 0.07 and rune.pvp == "full" and rune.ready


async def _equip(db, character_id, item):
    from models import Inventory

    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character_id, item_id=item.id, equipped=True))
    await db.flush()


async def test_modifiers_sum_runes_items_ring(db_session, make_character) -> None:
    c = await make_character()
    c.rune_effects = {"rune:tempered": 0.07, "rune:true_eye": 0.077, "rune:bitter_blood": 0.12}
    await _equip(db_session, c.id, Item(name="a", slot="weapon", craft_spec="dps", craft_resist="crit",
                                        craft_efficiency=120, base_stats={}))
    await _equip(db_session, c.id, Item(name="b", slot="armor", craft_spec="tank", craft_resist="dot",
                                        craft_efficiency=90, base_stats={}))
    # Не надетая вещь не считается.
    db_session.add(Item(name="c", slot="helmet", craft_spec="tank", craft_resist="dodge", craft_efficiency=120,
                        base_stats={}))
    await db_session.flush()
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods["resist_crit"] == pytest.approx(resists.capped(0.07 + 0.10))
    assert mods["accuracy"] == pytest.approx(0.077)
    assert mods["resist_dot"] == pytest.approx(resists.capped(0.12 + 0.075))
    c.resist_ring = True
    mods = await preset_service.resolve_active_modifiers(db_session, c, pvp=True)
    assert mods["resist_crit"] == pytest.approx(resists.capped(0.07 + 0.10 + 0.15))
    assert mods["accuracy"] == pytest.approx(resists.capped(0.077 + 0.15))
    # «Горькая кровь» в PvP вполсилы, как и раньше.
    assert mods["resist_dot"] == pytest.approx(resists.capped(0.06 + 0.075 + 0.15))


class _Lucky(random.Random):
    def random(self) -> float:
        return 0.00005


async def test_ring_drops_worn_then_to_bag(db_session, make_character) -> None:
    c = await make_character()
    assert await resist_service.maybe_drop_ring(db_session, c, _Lucky()) == "worn"
    assert c.resist_ring
    # Второй и третий (2026-11-02) - в сумку, это товар.
    assert await resist_service.maybe_drop_ring(db_session, c, _Lucky()) == "bag"
    assert await resist_service.maybe_drop_ring(db_session, c, _Lucky()) == "bag"
    assert await resist_service.spare_rings(db_session, c.id) == 2
    other = await make_character()
    assert await resist_service.maybe_drop_ring(db_session, other, random.Random(1)) is None
    payload = await resist_service.ring_payload(db_session, c)
    assert payload["name"] == resists.RING_TITLE and "15%" in payload["effect"]
    assert payload["worn"] and payload["spare"] == 2
    assert await resist_service.ring_payload(db_session, other) is None


async def test_ring_wear_remove_and_effect(db_session, make_character) -> None:
    c = await make_character()
    await resist_service.add_ring(db_session, c)
    await resist_service.remove(db_session, c)
    assert not c.resist_ring and await resist_service.spare_rings(db_session, c.id) == 1
    # Снятый не действует, но слот виден - из сумки можно надеть.
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods.get("resist_crit", 0.0) == 0.0
    payload = await resist_service.ring_payload(db_session, c)
    assert payload["worn"] is False and payload["spare"] == 1
    with pytest.raises(resist_service.RingError):
        await resist_service.remove(db_session, c)
    await resist_service.wear(db_session, c)
    assert c.resist_ring and await resist_service.spare_rings(db_session, c.id) == 0
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods["resist_crit"] == pytest.approx(0.15)
    # Второй на палец не надеть, и из пустой сумки тоже.
    with pytest.raises(resist_service.RingError):
        await resist_service.wear(db_session, c)
    await resist_service.remove(db_session, c)
    await resist_service.wear(db_session, c)
    with pytest.raises(resist_service.RingError):
        await resist_service.wear(db_session, c)


async def test_ring_transfer_only_spare(db_session, make_character) -> None:
    from services import transfer_service

    a, b = await make_character(), await make_character()
    await resist_service.add_ring(db_session, a)
    # Надетый не передаётся: в сумке пусто - предложения нет.
    lookup = await transfer_service.find(db_session, a.id, resists.RING_TITLE.lower())
    assert not lookup.offers
    await resist_service.add_ring(db_session, a)
    lookup = await transfer_service.find(db_session, a.id, resists.RING_TITLE.lower())
    (offer,) = lookup.offers
    assert offer.kind == "ring" and offer.available == 1
    assert offer.kind in transfer_service.NEEDS_NEAR
    await transfer_service.execute(db_session, a.id, b.id, offer, 1)
    assert a.resist_ring and await resist_service.spare_rings(db_session, a.id) == 0
    # Полученный лежит в сумке, надевается сам игрок.
    assert not b.resist_ring and await resist_service.spare_rings(db_session, b.id) == 1
    with pytest.raises(transfer_service.TransferFailed):
        await transfer_service.execute(db_session, a.id, b.id, offer, 1)


async def test_ring_on_market(db_session, make_character) -> None:
    from game.economy import market_config as mc
    from services import market_service

    key = f"craft:{resists.RING_ID}"
    assert mc.good(key).category == "treasure"
    assert any(c[0] == "treasure" for c in mc.CATEGORIES)
    c = await make_character()
    await resist_service.add_ring(db_session, c)
    assert key not in await market_service.holdings(db_session, c.id)  # надетый не продаётся
    await resist_service.add_ring(db_session, c)
    assert (await market_service.holdings(db_session, c.id))[key] == 1
    assert await market_service._take(db_session, c.id, key, 1)
    assert await resist_service.spare_rings(db_session, c.id) == 0 and c.resist_ring
    await market_service._give(db_session, c.id, key, 1)
    assert await resist_service.spare_rings(db_session, c.id) == 1


def test_craft_rolls_resist() -> None:
    item = Item(name="x", slot="weapon", craft_spec="dps", craft_efficiency=90, base_stats={})
    resist_service.roll_for(item, random.Random(3))
    assert item.craft_resist in resists.KINDS
    seen = {resists.roll(random.Random(s)) for s in range(30)}
    assert seen == set(resists.KINDS)


def test_derived_stats_show_resists() -> None:
    from services.derived_stats_service import compute

    class Ch:
        level, base_class, subclass = 60, "warrior", "guardian"

    class St:
        strength, agility, intellect, vitality, will = 10, 10, 10, 200, 10

    d = compute(Ch(), St(), mods={"resist_crit": 0.07, "accuracy": 0.1, "resist_dot": 2.0})
    assert d.crit_resist == pytest.approx(0.075 + 0.07)
    assert d.accuracy == pytest.approx(0.1) and d.dot_resist == pytest.approx(0.9)
