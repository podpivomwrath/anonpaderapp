"""Биржа: линейный шаг цены за блок, фикс-спред, убыточный round-trip."""

import pytest

from game.combat import balance_config as bc
from game.economy.exchange import Exchange, InMemoryExchangeState
from services.wallet_service import NotEnoughCurrency, get_wallet

BASE = bc.EXCHANGE_BASE_BUY_PRICE
STEP = bc.EXCHANGE_PRICE_STEP
BLOCK = bc.EXCHANGE_BLOCK_SIZE


def test_price_grows_linearly_per_block() -> None:
    assert Exchange.buy_price_at(0) == BASE
    assert Exchange.buy_price_at(BLOCK - 1) == BASE
    assert Exchange.buy_price_at(BLOCK) == BASE + STEP          # ступенька
    assert Exchange.buy_price_at(5 * BLOCK) == BASE + 5 * STEP  # линейно


def test_buy_cost_steps_across_blocks() -> None:
    # первый блок целиком по базовой цене
    assert Exchange.buy_cost(0, BLOCK) == BLOCK * BASE
    # полтора блока: 100 по BASE + 50 по BASE+STEP
    assert Exchange.buy_cost(0, BLOCK + 50) == BLOCK * BASE + 50 * (BASE + STEP)
    # покупка из середины блока
    assert Exchange.buy_cost(BLOCK // 2, BLOCK) == (
        (BLOCK // 2) * BASE + (BLOCK - BLOCK // 2) * (BASE + STEP)
    )


def test_fixed_spread() -> None:
    assert Exchange.buy_price_at(0) - Exchange.sell_price_at(0) == bc.EXCHANGE_SPREAD


def test_round_trip_is_lossy_math() -> None:
    """Купить → продать = гарантированный минус (п.10)."""
    for net_sold in (0, 50, 250, 1000):
        for amount in (1, 10, 150):
            cost = Exchange.buy_cost(net_sold, amount)
            gain = Exchange.sell_gain(net_sold + amount, amount)
            assert gain < cost, (net_sold, amount)


async def test_buy_and_sell_flow(db_session, make_character) -> None:
    character = await make_character(farm=100_000)
    exchange = Exchange(InMemoryExchangeState())

    order = await exchange.buy_donate(db_session, character.id, 50)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.donate_currency == 50
    assert wallet.farm_currency == 100_000 - order.gold_amount
    assert order.gold_amount == 50 * BASE

    # round-trip убыточен и на живом кошельке
    await exchange.sell_donate(db_session, character.id, 50)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.donate_currency == 0
    assert wallet.farm_currency < 100_000


async def test_buy_without_gold_fails(db_session, make_character) -> None:
    character = await make_character(farm=10)
    exchange = Exchange(InMemoryExchangeState())
    with pytest.raises(NotEnoughCurrency):
        await exchange.buy_donate(db_session, character.id, 100)


async def test_quote_moves_with_volume(db_session, make_character) -> None:
    character = await make_character(farm=10_000_000)
    exchange = Exchange(InMemoryExchangeState())
    q0 = await exchange.quote()
    await exchange.buy_donate(db_session, character.id, BLOCK * 3)
    q1 = await exchange.quote()
    assert q1.buy_price == q0.buy_price + 3 * STEP
    assert q1.block == 3


def test_start_price_is_5000_per_lot() -> None:
    assert Exchange.buy_cost(0, BLOCK) == 5000


def test_price_falls_when_players_sell_but_has_floor() -> None:
    assert Exchange.buy_price_at(-BLOCK) == BASE - STEP
    assert Exchange.buy_price_at(-10_000 * BLOCK) == bc.EXCHANGE_MIN_BUY_PRICE
    assert Exchange.sell_price_at(-10_000 * BLOCK) == bc.EXCHANGE_MIN_SELL_PRICE
    # Продажа из нуля идёт по нисходящим ступеням.
    assert Exchange.sell_gain(0, 2 * BLOCK) == BLOCK * (BASE - STEP - bc.EXCHANGE_SPREAD) + BLOCK * (
        BASE - 2 * STEP - bc.EXCHANGE_SPREAD
    )


async def test_service_lots_and_course(db_session, make_character) -> None:
    from services import exchange_service

    character = await make_character(farm=100_000, donate=500)
    q0 = await exchange_service.quote(db_session)
    assert q0.buy_lot == 5000 and q0.buy_series[1] == 5000 + 5000 + BLOCK * STEP
    with pytest.raises(exchange_service.ExchangeError):
        await exchange_service.buy(db_session, character, 0)
    order = await exchange_service.buy(db_session, character, 2)
    assert order.amount == 200 and order.gold_amount == q0.buy_series[1]
    q1 = await exchange_service.quote(db_session)
    assert q1.buy_lot > q0.buy_lot
    await exchange_service.sell(db_session, character, 3)
    q2 = await exchange_service.quote(db_session)
    assert q2.net_sold == -BLOCK and q2.buy_lot < q0.buy_lot
    with pytest.raises(exchange_service.ExchangeError, match="самоцветов"):
        await exchange_service.sell(db_session, character, 50)


async def test_sell_gems_is_taxed_by_guild(db_session, make_character) -> None:
    from game.economy import guild_config as gc
    from services import exchange_service, guild_service

    leader = await make_character(level=30, donate=gc.FOUND_COST_GEMS + 100)
    await guild_service.create(db_session, leader, "Торговцы", "ТРГ")
    await guild_service.set_tax(db_session, leader, 10)
    order = await exchange_service.sell(db_session, leader, 1)
    wallet = await get_wallet(db_session, leader.id)
    assert wallet.farm_currency == order.gold_amount - order.gold_amount // 10
    assert guild_service.gold_label(leader, 1000) == "1000 золота (после налога 900)"
