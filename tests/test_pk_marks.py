"""Кровавое клеймо (services/pk_service.py, 2026-10-15)."""

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


async def test_no_bounty_marks_cost_nothing_and_hunter_gets_nothing(db_session, make_character):
    """2026-10-16: награды за голову нет - метка ничего не списывает, убийство
    клеймёного ничего не платит."""
    killer = await make_character(level=30, farm=1000)
    weak = await make_character(level=10)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    assert killer.pk_marks == 2 and killer.pk_bounty == 0
    assert (await wallet_service.get_wallet(db_session, killer.id)).farm_currency == 1000

    hunter = await make_character(level=10)
    out = await pk_service.on_pvp_kill(db_session, hunter, killer, NOW)
    assert not out.branded and hunter.pk_marks == 0
    assert (await wallet_service.get_wallet(db_session, hunter.id)).farm_currency == 0
    assert (await wallet_service.get_wallet(db_session, killer.id)).farm_currency == 1000


async def test_legacy_escrow_returns_when_marks_gone(db_session, make_character):
    """Залог, оставшийся от прежней награды, возвращается при сходе меток."""
    killer = await make_character(level=30, farm=0)
    killer.pk_marks, killer.pk_marks_at, killer.pk_bounty = 1, NOW, 250
    await pk_service.settle(db_session, killer, NOW + timedelta(hours=5))
    assert killer.pk_marks == 0 and killer.pk_bounty == 0
    assert (await wallet_service.get_wallet(db_session, killer.id)).farm_currency == 250


async def test_marks_decay(db_session, make_character):
    killer = await make_character(level=30, farm=1000)
    weak = await make_character(level=10)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    assert pk_service.marks(killer, NOW + timedelta(hours=4)) == 2
    assert pk_service.marks(killer, NOW + timedelta(hours=5)) == 1
    await pk_service.settle(db_session, killer, NOW + timedelta(hours=10))
    assert killer.pk_marks == 0


async def test_thresholds(make_character):
    c = await make_character(level=40)
    c.pk_marks, c.pk_marks_at = 5, datetime.now(timezone.utc)
    assert pk_service.shop_mult(c) == pc.SHOP_PRICE_MULT
    assert pk_service.relic_mult(c) == pc.RELIC_SELL_MULT
    assert pk_service.costly_death(c) and not pk_service.city_banned(c)
    c.pk_marks = 20
    assert pk_service.city_banned(c)


async def test_mass_kill_summary_is_one_block(db_session, make_character):
    """2026-10-15: массовый бой - «Клеймо x2» и общая сумма, без абзаца на каждого."""
    killer = await make_character(level=30, farm=1000)
    a = await make_character(level=10)
    b = await make_character(level=10)
    outs = [await pk_service.on_pvp_kill(db_session, killer, v, NOW) for v in (a, b)]
    lines = pk_service.mass_killer_lines(killer, outs)
    assert len(lines) == 1
    assert "x2" in lines[0] and "меток: 2" in lines[0]


async def test_weak_attacker_who_lost_brands_nobody(db_session, make_character):
    """Слабый напал сам и погиб - это самооборона: ни метки, ни права мести
    (2026-10-20)."""
    defender = await make_character(level=40)
    attacker = await make_character(level=20)
    out = await pk_service.on_pvp_kill(db_session, defender, attacker, NOW, victim_attacked=True)
    assert not out.branded and defender.pk_marks == 0
    assert attacker.revenge_target_id is None
