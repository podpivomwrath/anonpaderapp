"""Курьер (2026-10-19): посылка списывается сразу, курьер бежит из города к
отправителю, потом к получателю, поворачивает за ним и ждёт конца боя."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.economy import courier_config as cc
from game.world import world_config as wc
from models import CharacterConsumable, CourierDelivery, Inventory, Item, TransferLog
from services import courier_service as cs
from services import elixir_service, transfer_service as ts

T0 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
STEP = timedelta(seconds=cc.SECONDS_PER_CELL)


async def _pair(make_character, sender_pos=(10, 0), recipient_pos=(-10, 5)):
    s = await make_character(level=30, donate=1000, region="ridge")
    r = await make_character(level=30, region="docks")
    s.pos_x, s.pos_y = sender_pos
    r.pos_x, r.pos_y = recipient_pos
    s.has_courier = True
    return s, r


async def _elixir_offer(db, character_id, n=5):
    await elixir_service.grant(db, character_id, "heal_small", n)
    return (await ts.find(db, character_id, "малое исцеление")).offers[0]


async def _run(db, until: datetime, busy=frozenset(), start=T0):
    events, t = [], start
    while t <= until:
        events += [e.kind for e in await cs.advance(db, set(busy), t)]
        t += STEP
    return events


def test_who_needs_courier() -> None:
    from types import SimpleNamespace

    a, near, far = (SimpleNamespace(pos_x=1, pos_y=1), SimpleNamespace(pos_x=1, pos_y=1),
                    SimpleNamespace(pos_x=2, pos_y=1))
    item = ts.Offer(kind="item", ref="1", label="Меч", available=1, stackable=False)
    gold = ts.Offer(kind="gold", ref=None, label="золото", available=500)
    assert not ts.needs_courier(item, a, near)
    assert ts.needs_courier(item, a, far)
    assert not ts.needs_courier(gold, a, far)  # валюта - на любое расстояние


async def test_parcel_is_taken_at_once_and_delivered(db_session, make_character) -> None:
    s, r = await _pair(make_character)
    offer = await _elixir_offer(db_session, s.id)
    d = await cs.send(db_session, s, r, offer, 3, reveal_sender=False, now=T0)
    assert (d.x, d.y) == wc.CITY_COORDS["ridge"] and d.phase == cs.PICKUP
    assert dict((e.id, n) for e, n in await elixir_service.get_stock(db_session, s.id))["heal_small"] == 2

    events = await _run(db_session, T0 + STEP * 200)
    assert events == ["picked", "delivered"]
    assert d.status == cs.DELIVERED and (d.x, d.y) == (r.pos_x, r.pos_y)
    got = await db_session.scalar(select(CharacterConsumable.count).where(
        CharacterConsumable.character_id == r.id, CharacterConsumable.elixir_id == "heal_small"))
    assert got == 3
    assert await db_session.scalar(select(TransferLog).where(TransferLog.to_character_id == r.id)) is not None


async def test_item_travels_without_owner(db_session, make_character) -> None:
    s, r = await _pair(make_character)
    item = Item(name="Меч гонца", slot="weapon", base_stats={"str": 5}, rarity="common", ilvl=None)
    db_session.add(item)
    await db_session.flush()
    db_session.add(Inventory(character_id=s.id, item_id=item.id, equipped=False))
    await db_session.flush()
    offer = ts.Offer(kind="item", ref=str(item.id), label=item.name, available=1, stackable=False)
    await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    # В пути вещь ничья: ни продать, ни передать второй раз.
    assert await db_session.scalar(select(Inventory).where(Inventory.item_id == item.id)) is None
    await _run(db_session, T0 + STEP * 200)
    owner = await db_session.scalar(select(Inventory.character_id).where(Inventory.item_id == item.id))
    assert owner == r.id


async def test_courier_turns_after_moving_recipient(db_session, make_character) -> None:
    """Получатель ушёл, пока курьер бежал, - курьер меняет цель в дороге."""
    s, r = await _pair(make_character, sender_pos=wc.CITY_COORDS["ridge"])
    offer = await _elixir_offer(db_session, s.id)
    d = await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    assert [e.kind for e in await cs.advance(db_session, set(), T0)] == ["picked"]
    await _run(db_session, T0 + STEP * 5, start=T0 + STEP)
    assert d.status == cs.ACTIVE
    r.pos_x, r.pos_y = 20, -15  # ушёл в другую сторону
    events = await _run(db_session, T0 + STEP * 300, start=T0 + STEP * 6)
    assert events == ["delivered"] and (d.x, d.y) == (20, -15)


async def test_courier_follows_moving_sender_for_pickup(db_session, make_character) -> None:
    s, r = await _pair(make_character)
    offer = await _elixir_offer(db_session, s.id)
    d = await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    await _run(db_session, T0 + STEP * 3)
    s.pos_x, s.pos_y = -5, -20
    await _run(db_session, T0 + STEP * 200, start=T0 + STEP * 4)
    assert d.status == cs.DELIVERED


async def test_waits_while_recipient_fights(db_session, make_character) -> None:
    s, r = await _pair(make_character, sender_pos=wc.CITY_COORDS["ridge"])
    offer = await _elixir_offer(db_session, s.id)
    d = await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    end = T0 + STEP * 200
    events = await _run(db_session, end, busy={r.id})
    assert events == ["picked", "waiting"] and d.status == cs.ACTIVE and d.waiting
    assert [e.kind for e in await cs.advance(db_session, set(), end + STEP)] == ["delivered"]


async def test_one_parcel_at_a_time_and_needs_courier(db_session, make_character) -> None:
    s, r = await _pair(make_character)
    offer = await _elixir_offer(db_session, s.id)
    await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    with pytest.raises(cs.CourierError):
        await cs.send(db_session, s, r, offer, 1, reveal_sender=False, now=T0)
    s.has_courier = False
    other = await make_character(region="woods")
    with pytest.raises(cs.CourierError):
        await cs.send(db_session, s, other, offer, 1, reveal_sender=False, now=T0)


async def test_returned_when_recipient_is_gone(db_session, make_character) -> None:
    s, r = await _pair(make_character)
    offer = await _elixir_offer(db_session, s.id, n=2)
    d = await cs.send(db_session, s, r, offer, 2, reveal_sender=False, now=T0)
    d.recipient_id = None  # персонажа удалили (FK обнуляется)
    d.phase = cs.DELIVER
    assert [e.kind for e in await cs.advance(db_session, set(), T0 + STEP)] == ["returned"]
    assert dict((e.id, n) for e, n in await elixir_service.get_stock(db_session, s.id))["heal_small"] == 2


async def test_courier_is_bought_once(db_session, make_character) -> None:
    c = await make_character(donate=1200)
    await cs.buy(db_session, c)
    assert c.has_courier
    with pytest.raises(cs.CourierError):
        await cs.buy(db_session, c)
    rows = (await db_session.scalars(select(CourierDelivery))).all()
    assert rows == []
