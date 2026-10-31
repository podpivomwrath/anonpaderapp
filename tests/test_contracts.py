"""Заказы на игроков (services/contract_service.py, 2026-10-16)."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Contract
from services import contract_service as cs
from services import pk_service
from services.wallet_service import get_wallet

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


async def _gems(db, cid):
    return (await get_wallet(db, cid)).donate_currency


async def test_create_validates_and_charges(db_session, make_character):
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    newbie = await make_character(level=10)
    for args, msg in [
        ((target.name, 4, 100), "Убийств"), ((target.name, 21, 100), "Убийств"),
        ((target.name, 5, 9), "от 10"), (("никого", 5, 100), "нет"),
        ((orderer.name, 5, 100), "Себя"), ((newbie.name, 5, 100), "15 уровня"),
        ((target.name, 5, 300), "Не хватает"),
    ]:
        with pytest.raises(cs.ContractError, match=msg):
            await cs.create(db_session, orderer, *args, now=NOW)
    assert await _gems(db_session, orderer.id) == 1000
    c = await cs.create(db_session, orderer, target.name, 5, 120, now=NOW)
    assert (c.target_id, c.kills_left, c.price) == (target.id, 5, 120)
    assert await _gems(db_session, orderer.id) == 400


async def test_take_rules(db_session, make_character):
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    hunter = await make_character(level=20)
    c = await cs.create(db_session, orderer, target.name, 5, 100, now=NOW)
    with pytest.raises(cs.ContractError, match="на тебя"):
        await cs.take(db_session, target, c.id, now=NOW)
    with pytest.raises(cs.ContractError, match="Свой"):
        await cs.take(db_session, orderer, c.id, now=NOW)
    await cs.take(db_session, hunter, c.id, now=NOW)
    with pytest.raises(cs.ContractError, match="уже взял"):
        await cs.take(db_session, hunter, c.id, now=NOW)
    assert await cs.hunted_ids(db_session, hunter.id, NOW) == {target.id}
    with pytest.raises(cs.ContractError, match="закрыт"):
        await cs.take(db_session, await make_character(), c.id, now=NOW + timedelta(hours=21))


async def test_kill_pays_split_and_closes(db_session, make_character):
    orderer = await make_character(level=20, donate=2000)
    target = await make_character(level=20)
    a = await make_character(level=20)
    b = await make_character(level=20)
    outsider = await make_character(level=20)
    c = await cs.create(db_session, orderer, target.name, 5, 301, now=NOW)
    await cs.take(db_session, a, c.id, now=NOW)
    await cs.take(db_session, b, c.id, now=NOW)
    # Бой: бил a, b и посторонний (без заказа) - делят только взявшие.
    payout = await cs.on_kill(db_session, target, [a.id, outsider.id, b.id], now=NOW)
    # 301 минус комиссия 10% (30) = 271: 136 + 135 (2026-10-24).
    assert await _gems(db_session, a.id) == 136 and await _gems(db_session, b.id) == 135
    assert await _gems(db_session, outsider.id) == 0
    assert c.kills_left == 4 and payout.victim_lines and payout.orderer_notes
    # Один охотник - вся сумма ему; последнее убийство закрывает заказ.
    payout = await cs.on_kill(db_session, target, [b.id], now=NOW)
    assert await _gems(db_session, b.id) == 135 + 271  # вся сумма за вычетом комиссии
    for _ in range(3):
        payout = await cs.on_kill(db_session, target, [b.id], now=NOW)
    assert c.status == "done" and payout.finished_for_target


async def test_kill_by_non_taker_pays_nothing(db_session, make_character):
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    stranger = await make_character(level=20)
    c = await cs.create(db_session, orderer, target.name, 5, 100, now=NOW)
    payout = await cs.on_kill(db_session, target, [stranger.id], now=NOW)
    assert not payout.hunter_lines and c.kills_left == 5


async def test_expired_contract_burns(db_session, make_character):
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    c = await cs.create(db_session, orderer, target.name, 5, 100, now=NOW)
    assert await cs.expire(db_session, NOW + timedelta(hours=19)) == []
    freed = await cs.expire(db_session, NOW + timedelta(hours=20, minutes=1))
    assert freed == [target.id] and c.status == "expired"
    assert await _gems(db_session, orderer.id) == 500  # сгорело, не вернулось
    assert await db_session.get(Contract, c.id) is not None


async def test_contract_kill_gives_no_brand(db_session, make_character):
    orderer = await make_character(level=40, donate=1000)
    target = await make_character(level=20)
    hunter = await make_character(level=40)
    c = await cs.create(db_session, orderer, target.name, 5, 100)
    await cs.take(db_session, hunter, c.id)
    out = await pk_service.on_pvp_kill(db_session, hunter, target)
    assert not out.branded and hunter.pk_marks == 0
    # Без заказа - клеймо как обычно.
    other = await make_character(level=40)
    assert (await pk_service.on_pvp_kill(db_session, other, target)).branded


async def test_afk_target_visible_only_to_hunter(db_session, make_character):
    from bot.handlers import pvp

    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    hunter = await make_character(level=20)
    stranger = await make_character(level=20)
    for c in (target, hunter, stranger):
        c.pos_x, c.pos_y = 3, 12
    target.last_active_at = None  # АФК
    await db_session.flush()
    c = await cs.create(db_session, orderer, target.name, 5, 100)
    await cs.take(db_session, hunter, c.id)
    hunter_view, _ = await pvp._scene_at(db_session, hunter)
    stranger_view, _ = await pvp._scene_at(db_session, stranger)
    assert target.id in {x.id for x in hunter_view}
    assert target.id not in {x.id for x in stranger_view}


async def test_event_vein_digger_visible_only_to_hunter(db_session, make_character):
    """2026-10-31: копающий жилу из исследования пропадает из «Осмотреться»,
    кроме как для взявшего на него заказ."""
    from bot.handlers import pvp

    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    hunter = await make_character(level=20)
    stranger = await make_character(level=20)
    for c in (target, hunter, stranger):
        c.pos_x, c.pos_y = 3, 12
    await db_session.flush()
    stranger_view, _ = await pvp._scene_at(db_session, stranger)
    assert target.id in {x.id for x in stranger_view}
    target.mining_ends_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    target.mining_mine_id = None
    await db_session.flush()
    c = await cs.create(db_session, orderer, target.name, 5, 100)
    await cs.take(db_session, hunter, c.id)
    hunter_view, _ = await pvp._scene_at(db_session, hunter)
    stranger_view, _ = await pvp._scene_at(db_session, stranger)
    assert target.id in {x.id for x in hunter_view}
    assert target.id not in {x.id for x in stranger_view}


async def test_guildmate_cannot_take_contract(db_session, make_character):
    from models import Guild

    guild = Guild(name="Своих не бьём", tag="СНБ")
    db_session.add(guild)
    await db_session.flush()
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20)
    mate = await make_character(level=20)
    target.guild_id = mate.guild_id = guild.id
    await db_session.flush()
    c = await cs.create(db_session, orderer, target.name, 5, 100)
    with pytest.raises(cs.ContractError, match="согильдиец"):
        await cs.take(db_session, mate, c.id)
    await cs.take(db_session, await make_character(level=20), c.id)  # чужой - может


async def test_buyout_burns_gems_reveals_name_and_blocks_reorder(db_session, make_character):
    """2026-11-01: откуп - x2 остатка, самоцветы сгорают, цель узнаёт ник
    заказчика, тот не заказывает её снова 24 часа."""
    orderer = await make_character(level=20, donate=1000)
    target = await make_character(level=20, donate=1000)
    hunter = await make_character(level=20)
    stranger = await make_character(level=20, donate=1000)
    c = await cs.create(db_session, orderer, target.name, 5, 10, now=NOW)
    await cs.take(db_session, hunter, c.id, now=NOW)
    await cs.on_kill(db_session, target, [hunter.id], now=NOW)  # осталось 4
    with pytest.raises(cs.ContractError, match="на себя"):
        await cs.buyout(db_session, stranger, c.id, now=NOW)
    out = await cs.buyout(db_session, target, c.id, now=NOW)
    assert out.cost == 4 * 10 * 2 and out.orderer_name == orderer.name and out.taker_ids == [hunter.id]
    assert await _gems(db_session, target.id) == 1000 - 80
    assert await _gems(db_session, orderer.id) == 1000 - 50  # заказчику ничего не вернулось
    assert c.status == "bought" and not await cs.is_target(db_session, target.id, NOW)
    with pytest.raises(cs.ContractError, match="закрыт"):
        await cs.buyout(db_session, target, c.id, now=NOW)
    with pytest.raises(cs.ContractError, match="откупился"):
        await cs.create(db_session, orderer, target.name, 5, 10, now=NOW + timedelta(hours=23))
    await cs.create(db_session, stranger, target.name, 5, 10, now=NOW + timedelta(hours=1))  # другим - можно
    await cs.create(db_session, orderer, target.name, 5, 10, now=NOW + timedelta(hours=25))
