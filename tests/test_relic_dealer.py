"""Пепельный меняла (2026-10-17): сделка на 25% дороже скупщика, 5% -
нападение особого противника, «Голод на реликвии» срывает часть партии."""

import random

import pytest

from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.world import relic_dealer as rd
from services import relic_dealer_service, trophy_service, wallet_service
from tests.conftest import NoCritRng, combatant


def test_stolen_share_is_capped_and_rounds_down_with_minimum_one():
    assert rd.stolen_from({"a": 10, "b": 3}, 0) == {}
    assert rd.stolen_from({"a": 10, "b": 3}, 2) == {"a": 2, "b": 1}
    assert rd.stolen_from({"a": 10}, 99) == {"a": 5}  # потолок 50%


def test_dealer_is_stronger_than_elite_and_steals_only_from_sellers():
    from game.world import encounters

    rng = random.Random(4)
    dealer = rd.build_dealer(2, 20, rng, sellers={1}).combatant
    elite = encounters.spawn_mob(3, "ridge", 30, 20, random.Random(4), elite=True).combatant
    assert dealer.max_hp > elite.max_hp
    seller = combatant(1, 0, vitality=200)
    bystander = combatant(5, 0, vitality=200)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    for c in (seller, bystander, dealer):
        state.add(c)
    skip = DeclaredAction(type=ActionType.SKIP)
    for _ in range(12):
        resolve_tick(state, {1: skip, 5: skip}, NoCritRng())
    assert 0 < rd.steals_of(dealer, 1) <= rd.max_steals()
    assert rd.steals_of(dealer, 5) == 0


async def test_sale_pays_bonus_over_appraiser_and_gives_no_xp(db_session, make_character):
    seller = await make_character(level=20, region="ridge")
    await trophy_service.grant_specific(db_session, seller.id, "blood_shard", 10)
    offer = await relic_dealer_service.offer(db_session, seller)
    assert offer[0][0] == relic_dealer_service.ALL
    xp_before = seller.experience
    gold, _progress = await relic_dealer_service.sell(db_session, seller, "blood_shard")
    base = trophy_service.trophy_def("blood_shard").sell_price * 10
    assert gold == pytest.approx(base * (1 + rd.PRICE_BONUS), rel=0.01)
    assert (await wallet_service.get_wallet(db_session, seller.id)).farm_currency == gold
    assert seller.experience == xp_before
    assert await trophy_service.get_stock(db_session, seller.id) == []


async def test_blood_brand_does_not_cut_dealer_price(db_session, make_character):
    from datetime import datetime, timezone

    seller = await make_character(level=20, region="ridge")
    seller.pk_marks, seller.pk_marks_at = 10, datetime.now(timezone.utc)
    assert await relic_dealer_service.price_mult(db_session, seller) == pytest.approx(1 + rd.PRICE_BONUS)


async def test_defeat_loses_only_stolen_part(db_session, make_character):
    seller = await make_character(level=20)
    await trophy_service.grant_specific(db_session, seller.id, "taint_clot", 20)
    lot = await relic_dealer_service.lot(db_session, seller, relic_dealer_service.ALL)
    taken = await relic_dealer_service.take_stolen(db_session, seller.id, rd.stolen_from(lot, 3))
    assert taken == {"taint_clot": 6}
    left = {d.id: n for d, n in await trophy_service.get_stock(db_session, seller.id)}
    assert left == {"taint_clot": 14}
    assert "уносит" in relic_dealer_service.stolen_line(taken)


def test_win_reward_is_mostly_experience():
    result = rd.win_result()
    assert result.xp == rd.WIN_MOBS == 20 and result.gold == 0 and result.reward == 0


async def test_win_loot_rolls_like_twenty_mobs(db_session, make_character):
    hero = await make_character(level=30)
    hero.pos_x, hero.pos_y = 5, 5
    lines = await relic_dealer_service.grant_win_loot(db_session, hero, 30, random.Random(2))
    stock = sum(n for _d, n in await trophy_service.get_stock(db_session, hero.id))
    assert stock > 0 and lines
