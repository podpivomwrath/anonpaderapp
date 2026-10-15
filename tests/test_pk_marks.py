"""Пепельное клеймо (services/pk_service.py, 2026-10-15)."""

from datetime import datetime, timedelta, timezone

from game.economy import pk_config as pc
from services import pk_service, wallet_service

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


async def test_kill_of_weaker_brands_and_gives_revenge(db_session, make_character):
    killer = await make_character(level=20, farm=1000)
    victim = await make_character(level=15)
    out = await pk_service.on_pvp_kill(db_session, killer, victim, NOW)
    assert out.branded and killer.pk_marks == 1 and killer.pk_bounty == 0
    assert victim.revenge_target_id == killer.id
    assert pk_service.revenge_bonus(victim, killer.id, NOW) == pc.REVENGE_BONUS
    assert pk_service.revenge_bonus(victim, killer.id, NOW + timedelta(hours=25)) == 0


async def test_close_levels_no_brand(db_session, make_character):
    killer = await make_character(level=20)
    victim = await make_character(level=16)
    out = await pk_service.on_pvp_kill(db_session, killer, victim, NOW)
    assert not out.branded and killer.pk_marks == 0


async def test_second_mark_freezes_bounty_and_hunter_claims_it(db_session, make_character):
    killer = await make_character(level=30, farm=1000)
    weak = await make_character(level=10)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    assert killer.pk_marks == 2
    assert killer.pk_bounty == 100  # 5% x 2 метки от 1000
    assert (await wallet_service.get_wallet(db_session, killer.id)).farm_currency == 900

    hunter = await make_character(level=10)  # младше на 20 - и всё равно без клейма
    out = await pk_service.on_pvp_kill(db_session, hunter, killer, NOW)
    assert out.bounty_claimed == 100 and not out.branded and hunter.pk_marks == 0
    assert killer.pk_bounty == 0


async def test_marks_decay_and_bounty_returns(db_session, make_character):
    killer = await make_character(level=30, farm=1000)
    weak = await make_character(level=10)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    assert pk_service.marks(killer, NOW + timedelta(hours=4)) == 2
    assert pk_service.marks(killer, NOW + timedelta(hours=5)) == 1
    refund = await pk_service.settle(db_session, killer, NOW + timedelta(hours=10))
    assert killer.pk_marks == 0 and refund == 100
    assert (await wallet_service.get_wallet(db_session, killer.id)).farm_currency == 1000


async def test_thresholds(make_character):
    c = await make_character(level=40)
    c.pk_marks, c.pk_marks_at = 5, datetime.now(timezone.utc)
    assert pk_service.shop_mult(c) == pc.SHOP_PRICE_MULT
    assert pk_service.relic_mult(c) == pc.RELIC_SELL_MULT
    assert pk_service.costly_death(c) and not pk_service.city_banned(c)
    c.pk_marks = 20
    assert pk_service.city_banned(c)
