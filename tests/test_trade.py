"""Торговые фирмы (2026-10-15): фирма, повозки, отправка, прибытие,
насыщение рынка, нападения, процветание городов."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.economy import faction_config as fc
from game.economy import trade_config as tc
from models import CharacterOre, TradeCart
from services import faction_service, trade_service
from services.wallet_service import get_wallet

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


class NoLuck(random.Random):
    """Ни нападений, ни ларцов."""

    def random(self) -> float:
        return 0.999


class AlwaysHit(random.Random):
    def random(self) -> float:
        return 0.0


async def trader(make_character, gold=200_000, level=20, region="ridge"):
    return await make_character(level=level, farm=gold, region=region)


async def firm_of(db, make_character, name="Соль и Камень", **kw):
    c = await trader(make_character, **kw)
    firm = await trade_service.buy_firm(db, c, name)
    return c, firm


async def test_firm_needs_level_gold_and_good_name(db_session, make_character) -> None:
    low = await trader(make_character, level=5)
    with pytest.raises(trade_service.TradeError, match="уровня"):
        await trade_service.buy_firm(db_session, low, "Фирма")
    poor = await trader(make_character, gold=100)
    with pytest.raises(trade_service.TradeError, match="стоит"):
        await trade_service.buy_firm(db_session, poor, "Бедняки")
    c = await trader(make_character)
    for bad in ("аб", "x" * 25, "Фирма!", "-фирма"):
        with pytest.raises(trade_service.TradeError):
            await trade_service.buy_firm(db_session, c, bad)
    firm = await trade_service.buy_firm(db_session, c, "  Соль   и Камень ")
    assert firm.name == "Соль и Камень" and firm.trade_level == 1
    assert (await get_wallet(db_session, c.id)).farm_currency == 200_000 - tc.FIRM_PRICE
    carts = await trade_service.carts(db_session, c.id)
    assert [(k.slot, k.city, k.status) for k in carts] == [(1, "ridge", "idle")]
    other = await trader(make_character)
    with pytest.raises(trade_service.TradeError, match="уже есть"):
        await trade_service.buy_firm(db_session, other, "СОЛЬ И КАМЕНЬ")


async def test_banned_name(db_session, make_character, monkeypatch) -> None:
    from services import onboarding_service

    monkeypatch.setattr(onboarding_service, "_banned_words", lambda: ("плохое",))
    c = await trader(make_character)
    with pytest.raises(trade_service.TradeError, match="не пройдёт"):
        await trade_service.buy_firm(db_session, c, "Очень Плохое Имя")


def test_route_economics() -> None:
    """Свой товар дёшево у производителя, сосед с дефицитом платит больше,
    дальний город - ещё больше (путь вдвое длиннее); у себя не покупают."""
    slate = tc.GOODS_BY_ID["ridge_slate"]
    buy = trade_service.city_buy_price("ridge", slate, 0)
    neighbour = trade_service.city_sell_price("docks", slate, 0)
    far = trade_service.city_sell_price("scorched", slate, 0)
    assert buy < neighbour < far
    assert trade_service.city_sell_price("ridge", slate, 0) is None
    assert trade_service.city_buy_price("docks", slate, 0) is None
    assert trade_service.city_sell_price("docks", slate, 10) == round(
        tc.TIER_BASE_PRICE[1] * tc.SELL_MULT_DEFICIT * (1 - tc.MAX_PRESSURE)
    )


def test_safe_route_is_slower_and_safer() -> None:
    cart = TradeCart(horses=1, body=1, plating=1, guard=1)
    short = trade_service.path("ridge", "docks", "short")
    safe = trade_service.path("ridge", "docks", "safe")
    assert trade_service.trip_seconds(cart, len(safe), "safe") > trade_service.trip_seconds(cart, len(short), "short")
    assert trade_service.ambush_chance(cart, safe) < trade_service.ambush_chance(cart, short)
    across = trade_service.path("ridge", "scorched", "short")
    assert trade_service.ambush_chance(cart, across) > trade_service.ambush_chance(cart, short)
    cart.guard = 5
    assert trade_service.ambush_chance(cart, short) < trade_service.ambush_chance(
        TradeCart(horses=1, body=1, plating=1, guard=1), short,
    )


async def test_dispatch_and_arrival(db_session, make_character) -> None:
    c, firm = await firm_of(db_session, make_character)
    gold0 = (await get_wallet(db_session, c.id)).farm_currency
    sent = await trade_service.dispatch(
        db_session, c, 1, "docks", "short", {"ridge_slate": 8}, NoLuck(), NOW,
    )
    assert sent.crates == 8 and sent.cost > 0
    cart = sent.cart
    assert cart.status == "traveling" and cart.to_city == "docks" and cart.ambushes == 0
    assert (await get_wallet(db_session, c.id)).farm_currency == gold0 - sent.cost
    with pytest.raises(trade_service.TradeError, match="в пути"):
        await trade_service.dispatch(db_session, c, 1, "woods", "short", {}, NoLuck(), NOW)

    # Раньше срока - ничего.
    assert await trade_service.tick(db_session, NoLuck(), NOW + timedelta(seconds=60)) == []
    arrivals = await trade_service.tick(db_session, NoLuck(), cart.arrives_at + timedelta(seconds=1))
    assert len(arrivals) == 1
    a = arrivals[0]
    assert a.crates == 8 and a.revenue > sent.cost and a.profit == a.revenue - sent.cost
    assert cart.status == "idle" and cart.city == "docks" and cart.cargo == {}
    assert (await get_wallet(db_session, c.id)).farm_currency == gold0 - sent.cost + a.revenue
    assert firm.profit_total == a.profit and firm.trade_xp == 8 * tc.XP_PER_CRATE[1]
    assert "прибыла в" in a.text() and "Продано 8" in a.text()
    trips = await trade_service.recent_trips(db_session, c.id)
    assert trips[0].crates == 8 and trips[0].to_city == "docks"


async def test_dispatch_rules(db_session, make_character) -> None:
    c, _ = await firm_of(db_session, make_character)
    with pytest.raises(trade_service.TradeError, match="не производят"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {"docks_salt": 1}, NoLuck(), NOW)
    with pytest.raises(trade_service.TradeError, match="уровня торговли"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {"ridge_icons": 1}, NoLuck(), NOW)
    with pytest.raises(trade_service.TradeError, match="влезет"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {"ridge_slate": 9}, NoLuck(), NOW)
    with pytest.raises(trade_service.TradeError, match="уже в этом"):
        await trade_service.dispatch(db_session, c, 1, "ridge", "short", {}, NoLuck(), NOW)
    with pytest.raises(trade_service.TradeError, match="путь"):
        await trade_service.dispatch(db_session, c, 1, "docks", "fast", {}, NoLuck(), NOW)
    with pytest.raises(trade_service.TradeError, match="Нет такой повозки"):
        await trade_service.dispatch(db_session, c, 2, "docks", "short", {}, NoLuck(), NOW)
    # Порожняком - можно.
    sent = await trade_service.dispatch(db_session, c, 1, "docks", "safe", {}, NoLuck(), NOW)
    assert sent.cost == 0 and sent.crates == 0


async def test_market_saturation(db_session, make_character) -> None:
    """Каждый ящик поднимает цену закупки и роняет цену продажи."""
    c, _ = await firm_of(db_session, make_character)
    first = await trade_service.dispatch(db_session, c, 1, "docks", "short", {"ridge_slate": 8}, NoLuck(), NOW)
    assert first.cost > 8 * trade_service.city_buy_price("ridge", tc.GOODS_BY_ID["ridge_slate"], 0)
    row = await trade_service.market_row(db_session, "ridge", "ridge_slate", lock=False, now=NOW)
    assert row.pressure == pytest.approx(8 * tc.SATURATION_PER_CRATE)
    later = await trade_service.market_row(db_session, "ridge", "ridge_slate", lock=False, now=NOW + timedelta(hours=1))
    assert later.pressure == pytest.approx(max(8 * tc.SATURATION_PER_CRATE - tc.RECOVERY_PER_HOUR, 0))


async def test_ambush_breaks_plating_and_loses_cargo(db_session, make_character) -> None:
    c, _ = await firm_of(db_session, make_character)
    sent = await trade_service.dispatch(db_session, c, 1, "scorched", "short", {"ridge_slate": 8}, AlwaysHit(), NOW)
    cart = sent.cart
    assert cart.ambushes >= 2
    [a] = await trade_service.tick(db_session, NoLuck(), cart.arrives_at)
    assert a.broke and a.lost and cart.durability == 0
    assert a.crates < 8 and "рассыпалось" in a.text()
    with pytest.raises(trade_service.TradeError, match="почини"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {}, NoLuck(), NOW)
    cost = await trade_service.repair(db_session, c, 1)
    assert cost == trade_service.max_durability(cart) * tc.REPAIR_PER_POINT
    assert cart.durability == trade_service.max_durability(cart)


async def test_upgrade_and_more_carts(db_session, make_character) -> None:
    c, firm = await firm_of(db_session, make_character, gold=1_000_000)
    with pytest.raises(trade_service.TradeError, match="руды"):
        await trade_service.upgrade(db_session, c, 1, "body")
    db_session.add(CharacterOre(character_id=c.id, ore_id="brown_iron", grade="common", count=10))
    await db_session.flush()
    cart = await trade_service.upgrade(db_session, c, 1, "body")
    assert trade_service.capacity(cart) == tc.PARTS_BY_ID["body"].values[1]

    with pytest.raises(trade_service.TradeError, match="уровня торговли"):
        await trade_service.buy_cart(db_session, c)
    firm.trade_level = 20
    second = await trade_service.buy_cart(db_session, c)
    third = await trade_service.buy_cart(db_session, c)
    assert (second.slot, third.slot) == (2, 3) and second.city == "ridge"
    with pytest.raises(trade_service.TradeError, match="больше не нужно"):
        await trade_service.buy_cart(db_session, c)


async def test_migrated_firm_must_be_named(db_session, make_character) -> None:
    from models import TradeFirm

    c = await trader(make_character)
    db_session.add(TradeFirm(character_id=c.id, trade_level=7, trade_xp=0, profit_total=0))
    db_session.add(trade_service._new_cart(c.id, 1, "ridge"))
    await db_session.flush()
    with pytest.raises(trade_service.TradeError, match="название"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {}, NoLuck(), NOW)
    firm = await trade_service.name_firm(db_session, c, "Старый Обоз")
    assert firm.name == "Старый Обоз" and firm.trade_level == 7
    with pytest.raises(trade_service.TradeError, match="менять"):
        await trade_service.name_firm(db_session, c, "Новый Обоз")


async def test_prosperity_goes_home_with_daily_cap(db_session, make_character) -> None:
    """Вклад - в РОДНОЙ город торговца, куда бы он ни возил; потолок в сутки."""
    c, firm = await firm_of(db_session, make_character, region="woods")
    before = (await faction_service.points(db_session, NOW))["woods"]
    credited = await faction_service.contribute(db_session, c, firm.trade_level, 30, NOW)
    assert credited == 30
    assert (await faction_service.points(db_session, NOW))["woods"] == pytest.approx(before + 30)
    # Потолок 100 на 1-9 уровне торговли: из 90 засчитается 70.
    assert await faction_service.contribute(db_session, c, firm.trade_level, 90, NOW) == 70
    assert await faction_service.contribute(db_session, c, firm.trade_level, 5, NOW) == 0
    assert await faction_service.today_points(db_session, c.id, NOW) == 100
    # Новые сутки (по Москве) - потолок снова свободен.
    assert await faction_service.contribute(db_session, c, firm.trade_level, 5, NOW + timedelta(days=1)) == 5


def test_daily_cap_grows_with_trade_level() -> None:
    assert fc.daily_cap(1) == 100 and fc.daily_cap(9) == 100
    assert fc.daily_cap(10) == 110 and fc.daily_cap(43) == 140


def test_prosperity_decay_and_tiers() -> None:
    later = NOW + timedelta(days=17)
    assert faction_service.decayed(4000, NOW, later) == pytest.approx(4000 * 0.96 ** 17)
    assert 1900 < faction_service.decayed(4000, NOW, later) < 2100
    assert fc.tier_for(0).id == "decline" and fc.tier_for(999).id == "decline"
    assert fc.tier_for(2000).id == "stagnation" and fc.tier_for(8000).id == "golden"
    assert fc.next_tier(2000).id == "plenty" and fc.next_tier(9000) is None


async def test_city_tier_changes_shop_and_relic_prices(db_session, make_character) -> None:
    from game.world import world_config as wc

    c = await make_character(level=30, region="docks")
    c.pos_x, c.pos_y = wc.CITY_COORDS["docks"]
    assert await faction_service.shop_mult(db_session, c) == 1.0
    await faction_service.add_points(db_session, "docks", 8_000, NOW)
    assert await faction_service.shop_mult(db_session, c) == pytest.approx(0.90)
    assert await faction_service.relic_mult(db_session, c) == pytest.approx(1.10)
    assert "Золотой век" in await faction_service.city_line(db_session, c, relics=True)
    c.pos_x, c.pos_y = 5, 5  # вне города - без надбавок
    assert await faction_service.relic_mult(db_session, c) == 1.0


async def test_arrival_feeds_home_city(db_session, make_character) -> None:
    c, _ = await firm_of(db_session, make_character, region="scorched")
    # Родной город - Предел, а повозка стоит в Кряже (перегнали) и везёт в Пристани.
    cart = (await trade_service.carts(db_session, c.id))[0]
    cart.city = "ridge"
    before = (await faction_service.points(db_session, NOW))
    sent = await trade_service.dispatch(db_session, c, 1, "docks", "short", {"ridge_slate": 8}, NoLuck(), NOW)
    at = sent.cart.arrives_at.replace(tzinfo=timezone.utc)
    [a] = await trade_service.tick(db_session, NoLuck(), at)
    after = await faction_service.points(db_session, at)
    assert a.prosperity == 8
    assert after["scorched"] == pytest.approx(fc.START_POINTS + 8)
    assert after["docks"] <= before["docks"] and after["ridge"] <= before["ridge"]


async def test_notify_settings(db_session, make_character) -> None:
    c, firm = await firm_of(db_session, make_character)
    await trade_service.set_notify(db_session, c, arrival=False, orders=True)
    assert firm.notify_arrival is False and firm.notify_orders is True
    sent = await trade_service.dispatch(db_session, c, 1, "docks", "short", {}, NoLuck(), NOW)
    [a] = await trade_service.tick(db_session, NoLuck(), sent.cart.arrives_at)
    assert a.notify is False


async def test_cart_position_along_path(db_session, make_character) -> None:
    from game.world import world_config as wc

    c, _ = await firm_of(db_session, make_character)
    cart = (await trade_service.carts(db_session, c.id))[0]
    assert trade_service.position(cart) == wc.CITY_COORDS["ridge"]
    sent = await trade_service.dispatch(db_session, c, 1, "docks", "short", {}, NoLuck(), NOW)
    mid = NOW + (sent.cart.arrives_at - NOW) / 2
    x, y = trade_service.position(sent.cart, mid)
    assert (x, y) not in (wc.CITY_COORDS["ridge"], wc.CITY_COORDS["docks"])


async def test_buy_without_name_then_name(db_session, make_character) -> None:
    """2026-10-15: фирму покупают без названия, название - следующим шагом."""
    c = await trader(make_character)
    firm = await trade_service.buy_firm(db_session, c)
    assert firm.name is None and firm.name_key is None
    with pytest.raises(trade_service.TradeError, match="название"):
        await trade_service.dispatch(db_session, c, 1, "docks", "short", {}, NoLuck(), NOW)
    await trade_service.name_firm(db_session, c, "Новая Лавка")
    assert firm.name == "Новая Лавка" and firm.name_key == "новая лавка"
