"""Торговля: повозка, Торговый дом, насыщение рынка, потери груза, грабёж, караваны."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.economy import trade_config as tc
from game.world import world_config as wc
from models import CharacterOre, MountTravel
from services import mount_service, trade_service
from services.wallet_service import get_wallet

RIDGE = wc.CITY_COORDS["ridge"]
DOCKS = wc.CITY_COORDS["docks"]


class NoLuck(random.Random):
    def random(self) -> float:
        return 0.999


async def trader(character_at, at=RIDGE, gold=200_000, level=20):
    return await character_at(*at, level=level, farm=gold)


async def test_cart_needs_city_level_and_gold(db_session, character_at) -> None:
    low = await trader(character_at, level=5)
    with pytest.raises(trade_service.TradeError, match="уровня"):
        await trade_service.buy_cart(db_session, low)
    field = await trader(character_at, at=(5, 5))
    with pytest.raises(trade_service.TradeError, match="Торговом доме"):
        await trade_service.buy_cart(db_session, field)
    c = await trader(character_at)
    cart = await trade_service.buy_cart(db_session, c)
    assert (cart.cart_x, cart.cart_y) == RIDGE and cart.durability == 2
    assert (await get_wallet(db_session, c.id)).farm_currency == 200_000 - tc.CART_PRICE
    with pytest.raises(trade_service.TradeError, match="уже есть"):
        await trade_service.buy_cart(db_session, c)


def test_route_economics() -> None:
    """Свой товар дёшево у производителя, дорого у соседа с дефицитом; в
    самом городе-производителе его не покупают."""
    slate = tc.GOODS_BY_ID["ridge_slate"]
    buy = trade_service.city_buy_price("ridge", slate, 0)
    sell_neighbour = trade_service.city_sell_price("docks", slate, 0)
    sell_far = trade_service.city_sell_price("scorched", slate, 0)
    assert buy < sell_far < sell_neighbour
    assert trade_service.city_sell_price("ridge", slate, 0) is None
    assert trade_service.city_buy_price("docks", slate, 0) is None
    # насыщение режет цену, но не ниже потолка
    assert trade_service.city_sell_price("docks", slate, 10) == round(
        tc.TIER_BASE_PRICE[1] * tc.SELL_MULT_DEFICIT * (1 - tc.MAX_PRESSURE)
    )


async def test_buy_sell_full_route(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    with pytest.raises(trade_service.TradeError, match="не производят"):
        await trade_service.buy(db_session, c, "docks_salt", 1)
    with pytest.raises(trade_service.TradeError, match="уровня торговли"):
        await trade_service.buy(db_session, c, "ridge_wool", 1)
    with pytest.raises(trade_service.TradeError, match="кузов"):
        await trade_service.buy(db_session, c, "ridge_slate", 7)
    deal = await trade_service.buy(db_session, c, "ridge_slate", 6)
    # цена каждого следующего ящика выше - покупка насыщает рынок
    first = trade_service.city_buy_price("ridge", tc.GOODS_BY_ID["ridge_slate"], 0)
    assert deal.gold > first * 6
    with pytest.raises(trade_service.TradeError, match="не покупает"):
        await trade_service.sell(db_session, c, "ridge_slate", 1)
    # приехали в Пристани (позиция повозки и игрока)
    cart = await trade_service.get_cart(db_session, c.id)
    c.pos_x, c.pos_y = DOCKS
    cart.cart_x, cart.cart_y = DOCKS
    sold = await trade_service.sell(db_session, c, "ridge_slate", 6, NoLuck())
    assert sold.profit > 0 and sold.xp == tc.XP_PER_CRATE[1] * 6
    assert cart.cargo == {} and cart.profit_total == sold.profit


async def test_trade_only_next_to_cart(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    c.pos_x, c.pos_y = DOCKS
    with pytest.raises(trade_service.TradeError, match="осталась"):
        await trade_service.buy(db_session, c, "docks_salt", 1)


async def test_upgrade_spends_gold_and_ore(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    with pytest.raises(trade_service.TradeError, match="руды"):
        await trade_service.upgrade(db_session, c, "body")
    db_session.add(CharacterOre(character_id=c.id, ore_id="brown_iron", grade="common", count=10))
    await db_session.flush()
    cart = await trade_service.upgrade(db_session, c, "body")
    assert cart.body == 2 and trade_service.capacity(cart) == 9


async def test_ambush_wears_plating_then_breaks_cargo(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    await trade_service.buy(db_session, c, "ridge_slate", 6)
    assert "держится" in await trade_service.on_ambush_won(db_session, c, NoLuck())
    line = await trade_service.on_ambush_won(db_session, c, NoLuck())
    cart = await trade_service.get_cart(db_session, c.id)
    assert "выбита" in line and trade_service.crates(cart) == 6 - 2  # 25% от 6 вверх = 2
    cost = await trade_service.repair(db_session, c)
    assert cost == 2 * tc.REPAIR_PER_POINT and cart.durability == 2


async def test_death_loses_part_and_cart_goes_home(db_session, character_at) -> None:
    c = await trader(character_at)
    c.region = "ridge"
    await trade_service.buy_cart(db_session, c)
    await trade_service.buy(db_session, c, "ridge_slate", 5)
    c.pos_x, c.pos_y = 12, 12
    line = await trade_service.on_death(db_session, c, NoLuck())
    cart = await trade_service.get_cart(db_session, c.id)
    assert trade_service.crates(cart) == 3 and "Пропало" in line
    assert (cart.cart_x, cart.cart_y) == RIDGE


async def test_robbery_only_deep_and_only_on_the_road(db_session, character_at) -> None:
    victim = await trader(character_at)
    victim.region = "ridge"
    robber = await trader(character_at, gold=0)
    await trade_service.buy_cart(db_session, victim)
    await trade_service.buy(db_session, victim, "ridge_slate", 6)
    # стоит в городе - не в пути, грабить нечего
    assert await trade_service.rob(db_session, robber, victim) == ({}, 0)
    await trade_service.send(db_session, victim, 0, 0)
    victim.pos_x, victim.pos_y = 0, 22  # кольцо 2
    assert await trade_service.rob(db_session, robber, victim) == ({}, 0)
    victim.pos_x, victim.pos_y = 0, 10  # кольцо 3
    lost, gold = await trade_service.rob(db_session, robber, victim, NoLuck())
    assert sum(lost.values()) == 2 and gold == round(2 * tc.TIER_BASE_PRICE[1] * tc.ROB_GOLD_SHARE)
    await trade_service.after_pvp_death(db_session, victim)
    cart = await trade_service.get_cart(db_session, victim.id)
    assert (cart.cart_x, cart.cart_y) == RIDGE and await trade_service.cart_travel(db_session, victim.id) is None


async def test_send_uses_horses_pace(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    travel = await trade_service.send(db_session, c, *DOCKS)
    assert travel.mount_id == tc.CART_MOUNT_ID and travel.step_seconds == 10.0
    with pytest.raises(trade_service.TradeError, match="в пути"):
        await trade_service.buy(db_session, c, "ridge_slate", 1)


async def test_caravan_trade(db_session, character_at) -> None:
    c = await trader(character_at)
    await trade_service.buy_cart(db_session, c)
    await trade_service.buy(db_session, c, "ridge_slate", 3)
    caravan = await trade_service.spawn_caravan(db_session, random.Random(1))
    caravan.buys = {"ridge_slate": 2}
    caravan.sells = {"docks_salt": 5}
    await db_session.flush()
    cart = await trade_service.get_cart(db_session, c.id)
    c.pos_x, c.pos_y = caravan.x, caravan.y
    cart.cart_x, cart.cart_y = caravan.x, caravan.y
    with pytest.raises(trade_service.TradeError, match="только 2"):
        await trade_service.sell(db_session, c, "ridge_slate", 3)
    deal = await trade_service.sell(db_session, c, "ridge_slate", 2, NoLuck())
    assert deal.gold == 2 * trade_service.caravan_sell_price(tc.GOODS_BY_ID["ridge_slate"])
    assert caravan.buys["ridge_slate"] == 0
    bought = await trade_service.buy(db_session, c, "docks_salt", 2)
    assert bought.gold == 2 * trade_service.caravan_buy_price(tc.GOODS_BY_ID["docks_salt"])


async def test_caravan_tick_respects_max(db_session) -> None:
    class Always(random.Random):
        def random(self) -> float:
            return 0.0

    rng = Always(3)
    for _ in range(tc.CARAVAN_MAX + 2):
        await trade_service.caravan_tick(db_session, rng)
    assert len(await trade_service.active_caravans(db_session)) == tc.CARAVAN_MAX


async def test_cart_ambush_follows_guard(db_session, character_at) -> None:
    c = await trader(character_at)
    cart = await trade_service.buy_cart(db_session, c)
    base = trade_service.trip_ambush(cart)
    cart.guard = 5
    assert trade_service.trip_ambush(cart) == pytest.approx(base * 0.4)
    travel = MountTravel(
        character_id=c.id, mount_id=tc.CART_MOUNT_ID, from_x=0, from_y=30, to_x=0, to_y=20,
        started_at=datetime.now(timezone.utc), arrives_at=datetime.now(timezone.utc) + timedelta(seconds=100),
        status="traveling", step_seconds=10.0, cell_index=0, next_cell_at=datetime.now(timezone.utc),
    )

    class Always(random.Random):
        def random(self) -> float:
            return 0.0

    step = mount_service.advance(travel, c, Always(), trip_chance=trade_service.trip_ambush(cart))
    assert step.ambushed  # клетка (0;29) не мирная - нападение разыгралось с шансом охраны
