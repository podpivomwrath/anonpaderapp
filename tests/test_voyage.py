"""Долгие путешествия (AFK): родной город, покупка, ежечасные события, возврат."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.economy import voyage_config as vc
from game.world import world_config as wc
from services import pvp_service, voyage_service
from services.wallet_service import get_wallet

NOW = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)


async def traveler(character_at, region="docks", level=30, gold=500_000):
    c = await character_at(*wc.CITY_COORDS[region], level=level, farm=gold)
    c.region = region
    return c


def test_every_city_has_a_full_voyage() -> None:
    for region in wc.CITY_COORDS:
        trip = vc.VOYAGES[region]
        assert set(trip.parts) == set(vc.PARTS_BY_ID)
        assert set(trip.events) == set(vc.TIER_WEIGHTS)
        for tier, events in trip.events.items():
            assert len(events) >= 3, (region, tier)
            for text, kind in events:
                assert kind in {*vc.XP_MOBS, *vc.GOLD_BASE, *vc.TROPHY_OF, "chest"}, (region, text)


async def test_only_from_home_city(db_session, character_at) -> None:
    c = await traveler(character_at)
    c.pos_x, c.pos_y = wc.CITY_COORDS["ridge"]  # чужой город
    with pytest.raises(voyage_service.VoyageError, match="родном"):
        await voyage_service.buy(db_session, c)
    c.pos_x, c.pos_y = wc.CITY_COORDS["docks"]
    await voyage_service.buy(db_session, c)
    assert (await get_wallet(db_session, c.id)).farm_currency == 500_000 - vc.VOYAGE_PRICE


async def test_hourly_events_rewards_and_end(db_session, character_at) -> None:
    c = await traveler(character_at)
    await voyage_service.buy(db_session, c)
    voyage = await voyage_service.start(db_session, c, now=NOW)
    assert voyage.status == "away" and voyage_service.total_hours(voyage) == 8
    assert await voyage_service.tick(db_session, random.Random(1), now=NOW + timedelta(minutes=30)) == []
    notices = await voyage_service.tick(db_session, random.Random(1), now=NOW + timedelta(minutes=61))
    assert len(notices) == 1 and notices[0].text.startswith("⛵ Час 1 из 8.")
    # бот лежал - все пропущенные часы догоняются, и поход кончается сам
    notices = await voyage_service.tick(db_session, random.Random(2), now=NOW + timedelta(hours=9))
    assert [n.finished for n in notices] == [False] * 7 + [True]
    assert voyage.status == "home" and voyage.hours_done == 8 and voyage.voyages_total == 1
    assert "За поход" in notices[-1].text and (voyage.trip_xp > 0 or voyage.trip_gold > 0)


async def test_come_back_any_time(db_session, character_at) -> None:
    c = await traveler(character_at, region="woods")
    await voyage_service.buy(db_session, c)
    await voyage_service.start(db_session, c, now=NOW)
    text = await voyage_service.come_back(db_session, c)
    assert "опушке" in text and "За поход" in text
    with pytest.raises(voyage_service.VoyageError):
        await voyage_service.come_back(db_session, c)


async def test_upgrades_gold_only(db_session, character_at) -> None:
    c = await traveler(character_at, region="ridge")
    voyage = await voyage_service.buy(db_session, c)
    await voyage_service.upgrade(db_session, c, "endurance")
    assert voyage_service.part_value(voyage, "endurance") == 10
    voyage = await voyage_service.start(db_session, c, now=NOW)
    assert voyage_service.total_hours(voyage) == 10
    with pytest.raises(voyage_service.VoyageError, match="в пути"):
        await voyage_service.upgrade(db_session, c, "haul")


async def test_away_players_are_not_seen_in_city(db_session, character_at) -> None:
    away = await traveler(character_at)
    other = await traveler(character_at)
    await voyage_service.buy(db_session, away)
    assert away.id in {c.id for c in await pvp_service.others_at(db_session, other)}
    await voyage_service.start(db_session, away, now=NOW)
    await db_session.flush()
    assert away.id not in {c.id for c in await pvp_service.others_at(db_session, other)}


async def test_legendary_events_are_rare_but_happen(db_session, character_at) -> None:
    c = await traveler(character_at, region="scorched")
    voyage = await voyage_service.buy(db_session, c)
    rng = random.Random(7)
    tiers = [voyage_service._roll_event(voyage, rng)[0] for _ in range(5000)]
    share = tiers.count("legendary") / len(tiers)
    assert 0.01 < share < 0.035
