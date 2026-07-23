"""Смерть/респавн (п.5) и ставки PvP (п.4)."""

from datetime import datetime, timedelta, timezone

from game.combat import balance_config as bc
from services.death_service import apply_death, is_dead, respawn_if_ready
from services.stake_service import settle_stakes
from services.wallet_service import get_wallet

NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


async def test_death_costs_experience_and_time(db_session, make_character) -> None:
    character = await make_character(level=1, experience=1000)
    apply_death(character, now=NOW)
    assert character.experience == 800  # -20% опыта текущего уровня
    assert character.respawn_at == NOW + timedelta(minutes=1)  # 1 мин на 1 ур.


async def test_respawn_time_scales_with_level(db_session, make_character) -> None:
    character = await make_character(level=100)
    apply_death(character, now=NOW)
    assert character.respawn_at == NOW + timedelta(minutes=30)  # 30 мин на 100 ур.


async def test_dead_then_respawn(db_session, make_character) -> None:
    character = await make_character(level=1)
    apply_death(character, now=NOW)
    assert is_dead(character, now=NOW + timedelta(seconds=30))
    assert not respawn_if_ready(character, now=NOW + timedelta(seconds=30))
    assert respawn_if_ready(character, now=NOW + timedelta(minutes=2))
    assert character.respawn_at is None
    assert not is_dead(character, now=NOW + timedelta(minutes=2))


async def test_stakes_move_percent_to_winner(db_session, make_character) -> None:
    winner = await make_character(farm=0)
    loser = await make_character(farm=1000)
    transfers = await settle_stakes(db_session, 1, [winner.id], [loser.id])

    expected = int(1000 * bc.PVP_STAKE_PERCENT)
    assert len(transfers) == 1 and transfers[0].amount == expected
    assert (await get_wallet(db_session, loser.id)).farm_currency == 1000 - expected
    assert (await get_wallet(db_session, winner.id)).farm_currency == expected


async def test_group_stakes_split_between_winners(db_session, make_character) -> None:
    w1 = await make_character(farm=0)
    w2 = await make_character(farm=0)
    loser = await make_character(farm=1010)
    await settle_stakes(db_session, 2, [w1.id, w2.id], [loser.id])

    stake = int(1010 * bc.PVP_STAKE_PERCENT)  # 101
    got1 = (await get_wallet(db_session, w1.id)).farm_currency
    got2 = (await get_wallet(db_session, w2.id)).farm_currency
    assert got1 + got2 == stake
    assert abs(got1 - got2) <= 1  # остаток — первому


async def test_draw_means_no_transfers(db_session, make_character) -> None:
    """При ничьей сервис не вызывается; пустые стороны — тоже ноль переводов."""
    someone = await make_character(farm=1000)
    assert await settle_stakes(db_session, 3, [], [someone.id]) == []
    assert (await get_wallet(db_session, someone.id)).farm_currency == 1000


async def test_broke_loser_transfers_nothing(db_session, make_character) -> None:
    winner = await make_character(farm=0)
    loser = await make_character(farm=0)
    assert await settle_stakes(db_session, 4, [winner.id], [loser.id]) == []
