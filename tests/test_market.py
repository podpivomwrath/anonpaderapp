"""Рынок (2026-10-23): заявки, витрина, комиссии, ящик купленного."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.economy import market_config as mc
from models import CharacterLootbox, CharacterOre, MarketInbox
from services import item_service, market_service as ms, mining_service, wallet_service

ORE = "ore:salt_quartz:common"


async def _gold(db, c) -> int:
    return (await wallet_service.get_wallet(db, c.id)).farm_currency


async def _ore(db, c) -> int:
    row = await db.scalar(select(CharacterOre).where(
        CharacterOre.character_id == c.id, CharacterOre.ore_id == "salt_quartz", CharacterOre.grade == "common",
    ))
    return row.count if row else 0


async def _pair(make_character, db):
    seller = await make_character(farm=10_000)
    buyer = await make_character(farm=10_000)
    await mining_service.add_ore(db, seller.id, "salt_quartz", "common", 50)
    return seller, buyer


async def test_buy_hits_resting_sell_at_its_price(db_session, make_character) -> None:
    seller, buyer = await _pair(make_character, db_session)
    await ms.place_sell(db_session, seller, ORE, 20, 100)
    assert await _ore(db_session, seller) == 30  # товар ушёл на рынок
    assert await _gold(db_session, seller) == 10_000 - 20  # 1% за выставление

    res = await ms.place_buy(db_session, buyer, ORE, 10, 150)
    assert res.filled == 10 and res.gold == 1000
    # Купил по цене продавца: 1500 удержано, 500 вернулось, плюс 1% от 1500.
    assert await _gold(db_session, buyer) == 10_000 - 15 - 1000
    assert await _gold(db_session, seller) == 10_000 - 20 + 950  # 5% с выручки
    inbox = await ms.inbox(db_session, buyer.id)
    assert [(i.good, i.qty) for i in inbox] == [(ORE, 10)]
    assert res.order.status == ms.FILLED


async def test_sell_hits_resting_buy_partially(db_session, make_character) -> None:
    seller, buyer = await _pair(make_character, db_session)
    buy = (await ms.place_buy(db_session, buyer, ORE, 30, 200)).order
    res = await ms.place_sell(db_session, seller, ORE, 10, 150)
    assert res.filled == 10 and res.gold == 1900  # по цене покупателя, минус 5%
    assert buy.qty_left == 20 and buy.status == ms.OPEN


async def test_own_orders_do_not_match(db_session, make_character) -> None:
    seller, _ = await _pair(make_character, db_session)
    await ms.place_sell(db_session, seller, ORE, 5, 100)
    res = await ms.place_buy(db_session, seller, ORE, 5, 200)
    assert res.filled == 0


async def test_limits_and_minimum(db_session, make_character) -> None:
    seller, _ = await _pair(make_character, db_session)
    with pytest.raises(ms.MarketError):
        await ms.place_sell(db_session, seller, ORE, 1, 50)  # меньше 100 золота
    with pytest.raises(ms.MarketError):
        await ms.place_sell(db_session, seller, ORE, 999, 100)  # столько нет
    for _ in range(mc.MAX_ORDERS):
        await ms.place_sell(db_session, seller, ORE, 1, 100)
    with pytest.raises(ms.MarketError):
        await ms.place_sell(db_session, seller, ORE, 1, 100)


async def test_cancel_and_expiry_return_everything(db_session, make_character) -> None:
    seller, buyer = await _pair(make_character, db_session)
    sell = (await ms.place_sell(db_session, seller, ORE, 10, 100)).order
    await ms.cancel(db_session, seller, sell.id)
    assert await _ore(db_session, seller) == 50
    buy = (await ms.place_buy(db_session, buyer, ORE, 10, 100)).order
    buy.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    notices = await ms.expire_due(db_session)
    assert buy.status == ms.EXPIRED and notices and notices[0].character_id == buyer.id
    assert await _gold(db_session, buyer) == 10_000 - 10  # вернулось всё, кроме 1%


async def test_claim_only_in_city(db_session, make_character) -> None:
    seller, buyer = await _pair(make_character, db_session)
    await ms.place_sell(db_session, seller, ORE, 5, 100)
    await ms.place_buy(db_session, buyer, ORE, 5, 100)
    buyer.pos_x, buyer.pos_y = 5, 5
    with pytest.raises(ms.MarketError):
        await ms.claim(db_session, buyer)
    buyer.pos_x, buyer.pos_y = 0, 30
    assert await ms.claim(db_session, buyer)
    assert await _ore(db_session, buyer) == 5
    assert not (await db_session.scalars(select(MarketInbox).where(MarketInbox.character_id == buyer.id))).all()


async def test_chests_are_one_good(db_session, make_character) -> None:
    seller = await make_character(farm=1000)
    buyer = await make_character(farm=1000)
    db_session.add(CharacterLootbox(character_id=seller.id, status="closed", kind="ashen", streak=40))
    await db_session.flush()
    assert (await ms.holdings(db_session, seller.id))["chest:ashen"] == 1
    await ms.place_sell(db_session, seller, "chest:ashen", 1, 300)
    await ms.place_buy(db_session, buyer, "chest:ashen", 1, 300)
    buyer.pos_x, buyer.pos_y = 0, 30
    await ms.claim(db_session, buyer)
    chests = (await db_session.scalars(select(CharacterLootbox).where(
        CharacterLootbox.character_id == buyer.id, CharacterLootbox.status == "closed",
    ))).all()
    assert len(chests) == 1 and chests[0].kind == "ashen"


async def test_showcase_unique_only(db_session, make_character) -> None:
    seller = await make_character(farm=1000, level=60)
    buyer = await make_character(farm=5000)
    unique_id = next(iter(item_service.unique_items()))
    item = await item_service.grant_unique_item(db_session, seller, unique_id)
    common = await item_service.grant_random_item(db_session, seller, 20, __import__("random").Random(1), rarity_id="common")
    with pytest.raises(ms.MarketError):
        await ms.list_item(db_session, seller, common.id, 500)
    lot = (await ms.list_item(db_session, seller, item.id, 2000)).order
    assert await item_service.get_inventory_entry(db_session, seller.id, item.id) is None
    res = await ms.buy_item(db_session, buyer, lot.id)
    assert lot.status == ms.FILLED and res.gold == 2000
    assert await _gold(db_session, seller) == 1000 - 20 + 1900
    buyer.pos_x, buyer.pos_y = 30, 0
    await ms.claim(db_session, buyer)
    assert await item_service.get_inventory_entry(db_session, buyer.id, item.id) is not None


def test_catalog_has_goods_of_every_category() -> None:
    cats = {g.category for g in mc.goods().values()}
    assert cats == {c for c, _ in mc.CATEGORIES}
    assert "chest:ashen" in mc.goods()


def test_every_good_has_a_page() -> None:
    """2026-10-24: у каждого товара рынка есть страничка - описание или
    что даёт (еда - бафф)."""
    from bot.miniapp_market_api import _about
    from game.economy import market_config as mc

    for key in mc.goods():
        about = _about(key)
        assert about["description"] or about["effect"], key
        if key.startswith("food:"):
            assert about["effect"], key


async def test_courier_brings_the_box(db_session, make_character) -> None:
    """2026-10-24, владелец: «Принести курьером» - ящик уходит курьеру, а
    курьер отдаёт товар там, где игрок стоит, не в городе."""
    from services import courier_service

    seller, buyer = await _pair(make_character, db_session)
    await ms.place_sell(db_session, seller, ORE, 5, 100)
    await ms.place_buy(db_session, buyer, ORE, 5, 100)
    buyer.pos_x, buyer.pos_y = 5, 5
    with pytest.raises(ms.MarketError):
        await ms.send_courier(db_session, buyer)  # курьера нет
    buyer.has_courier = True
    assert await ms.send_courier(db_session, buyer)
    assert not (await db_session.scalars(select(MarketInbox).where(MarketInbox.character_id == buyer.id))).all()
    with pytest.raises(ms.MarketError):
        await ms.send_courier(db_session, buyer)  # курьер занят, ящик пуст
    assert await _ore(db_session, buyer) == 0
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    events = await courier_service.advance(db_session, set(), now=later)
    assert [e.kind for e in events] == ["delivered"]
    assert await _ore(db_session, buyer) == 5
