"""Биржа: курс в процентах за лот, спред, отсутствие выгоды от кругов и сговора."""

import pytest

from game.combat import balance_config as bc
from game.economy.exchange import Exchange, InMemoryExchangeState
from services.wallet_service import NotEnoughCurrency, get_wallet

LOT = bc.EXCHANGE_BLOCK_SIZE
START = bc.EXCHANGE_START_LOT_PRICE
G = bc.EXCHANGE_LOT_GROWTH


def test_start_price_is_5000_per_lot() -> None:
    assert Exchange.buy_cost(0, LOT) == START == 5000


def test_price_moves_in_percent() -> None:
    assert Exchange.lot_buy_price(1) == round(START * (1 + G))
    assert Exchange.lot_buy_price(10) == round(START * (1 + G) ** 10)
    assert Exchange.lot_buy_price(-10) == round(START * (1 + G) ** -10)
    # каждый следующий лот дороже предыдущего на одну и ту же долю
    ratio = Exchange.lot_buy_price(51) / Exchange.lot_buy_price(50)
    assert abs(ratio - (1 + G)) < 0.001


def test_floor() -> None:
    assert Exchange.lot_buy_price(-10_000) == bc.EXCHANGE_MIN_LOT_PRICE
    assert Exchange.lot_sell_price(-10_000) < bc.EXCHANGE_MIN_LOT_PRICE


def test_extreme_levels_do_not_overflow() -> None:
    """Курс на запредельных ступенях не роняет float и влезает в BIGINT."""
    for level in (10**6, 10**400, -(10**400)):
        buy = Exchange.lot_buy_price(level)
        assert bc.EXCHANGE_MIN_LOT_PRICE <= buy <= bc.EXCHANGE_MAX_LOT_PRICE
        assert Exchange.lot_sell_price(level) < buy
    assert Exchange.buy_cost(10**9 * LOT, 50 * LOT) < 2**63


def test_sell_is_spread_below_buy_one_step_down() -> None:
    for level in (-200, -1, 0, 1, 37, 300):
        assert Exchange.lot_sell_price(level) == round(
            Exchange.lot_buy_price(level - 1) * (1 - bc.EXCHANGE_SPREAD_PCT)
        )


def test_no_profitable_round_trip_anywhere() -> None:
    """Купить k лотов и продать их обратно - всегда минус, на любом уровне
    курса и объёме, включая пол."""
    for level in range(-400, 400, 9):
        net = level * LOT
        for lots in (1, 2, 5, 10, 50):
            cost = Exchange.buy_cost(net, lots * LOT)
            gain = Exchange.sell_gain(net + lots * LOT, lots * LOT)
            assert gain < cost, (level, lots)


def test_collusion_loses_in_total() -> None:
    """Б заранее купил, А разгоняет цену, Б продаёт на вершине, А сбрасывает:
    вместе они в минусе - биржа денег не создаёт."""
    for start in (-100, 0, 100):
        for pre in (1, 5, 20):
            for push in (1, 10, 50):
                net = start * LOT
                b_cost = Exchange.buy_cost(net, pre * LOT)
                net += pre * LOT
                a_cost = Exchange.buy_cost(net, push * LOT)
                net += push * LOT
                b_gain = Exchange.sell_gain(net, pre * LOT)
                net -= pre * LOT
                a_gain = Exchange.sell_gain(net, push * LOT)
                assert (b_gain - b_cost) + (a_gain - a_cost) < 0, (start, pre, push)


async def test_buy_and_sell_flow(db_session, make_character) -> None:
    character = await make_character(farm=100_000)
    exchange = Exchange(InMemoryExchangeState())
    order = await exchange.buy_donate(db_session, character.id, LOT)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.donate_currency == LOT and order.gold_amount == START
    await exchange.sell_donate(db_session, character.id, LOT)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.donate_currency == 0 and wallet.farm_currency < 100_000


async def test_only_whole_lots(db_session, make_character) -> None:
    character = await make_character(farm=100_000)
    exchange = Exchange(InMemoryExchangeState())
    with pytest.raises(ValueError):
        await exchange.buy_donate(db_session, character.id, 150)


async def test_buy_without_gold_fails(db_session, make_character) -> None:
    character = await make_character(farm=10)
    exchange = Exchange(InMemoryExchangeState())
    with pytest.raises(NotEnoughCurrency):
        await exchange.buy_donate(db_session, character.id, LOT)


async def test_service_lots_and_course(db_session, make_character) -> None:
    from services import exchange_service

    character = await make_character(farm=100_000, donate=500)
    q0 = await exchange_service.quote(db_session)
    assert q0.buy_lot == START and q0.buy_series[1] == START + Exchange.lot_buy_price(1)
    with pytest.raises(exchange_service.ExchangeError):
        await exchange_service.buy(db_session, character, 0)
    order = await exchange_service.buy(db_session, character, 2)
    assert order.amount == 200 and order.gold_amount == q0.buy_series[1]
    q1 = await exchange_service.quote(db_session)
    assert q1.buy_lot == Exchange.lot_buy_price(2)
    await exchange_service.sell(db_session, character, 3)
    q2 = await exchange_service.quote(db_session)
    assert q2.net_sold == -LOT and q2.buy_lot < START
    with pytest.raises(exchange_service.ExchangeError, match="самоцветов"):
        await exchange_service.sell(db_session, character, 50)


async def test_exchange_is_not_taxed_by_guild(db_session, make_character) -> None:
    """Налог гильдии биржу не касается: выручка с продажи приходит целиком."""
    from game.economy import guild_config as gc
    from models import Guild
    from services import exchange_service, guild_service

    leader = await make_character(level=30, donate=gc.FOUND_COST_GEMS + 100)
    guild = await guild_service.create(db_session, leader, "Торговцы", "ТРГ")
    await guild_service.set_tax(db_session, leader, 10)
    order = await exchange_service.sell(db_session, leader, 1)
    wallet = await get_wallet(db_session, leader.id)
    assert wallet.farm_currency == order.gold_amount
    assert (await db_session.get(Guild, guild.id)).tax_collected == 0


async def test_daily_snapshot(db_session, make_character) -> None:
    from datetime import timedelta

    from services import exchange_service

    character = await make_character(farm=100_000)
    await exchange_service.buy(db_session, character, 2)
    today = exchange_service.yesterday_msk() + timedelta(days=1)
    row = await exchange_service.snapshot_day(db_session, today)
    assert row.bought_lots == 2 and row.buy_lot == Exchange.lot_buy_price(2)
    # Вчера сделок не было, а курс на его конец - до сегодняшних покупок.
    row = await exchange_service.snapshot_day(db_session, today - timedelta(days=1))
    assert row.bought_lots == 0 and row.buy_lot == START
    chart = await exchange_service.daily_chart(db_session)
    assert [r.day for r in chart] == [today - timedelta(days=1), today]


async def test_chart_points_only_closed_days(db_session, make_character) -> None:
    from datetime import timedelta

    from services import exchange_service

    character = await make_character(farm=100_000)
    old = await exchange_service.buy(db_session, character, 1)
    old.created_at = exchange_service.today_start_msk() - timedelta(hours=3)
    await exchange_service.buy(db_session, character, 1)  # сегодняшняя - на графике её ещё нет
    await db_session.flush()
    await exchange_service.snapshot_day(db_session, exchange_service.yesterday_msk())
    points = await exchange_service.chart_points(db_session)
    kinds = [p["kind"] for p in points]
    assert kinds == ["buy", "close"]
    assert points[0]["buy"] == Exchange.lot_buy_price(1) and points[1]["buy"] == Exchange.lot_buy_price(1)


async def test_fill_missing_days(db_session, make_character) -> None:
    from datetime import timedelta

    from services import exchange_service

    y = exchange_service.yesterday_msk()
    await exchange_service.snapshot_day(db_session, y - timedelta(days=3))
    written = await exchange_service.fill_missing_days(db_session)
    assert written == [y - timedelta(days=2), y - timedelta(days=1), y]
    assert await exchange_service.fill_missing_days(db_session) == []
