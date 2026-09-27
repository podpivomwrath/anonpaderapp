"""Ларец в сумке (патч 106): выдаётся закрытым, открывает игрок рулеткой."""

import random

import pytest

from services import lootbox_service as ls
from services import wallet_service


async def test_grant_puts_a_closed_chest_and_gives_nothing_yet(db_session, make_character) -> None:
    c = await make_character(farm=0)
    await ls.grant_chest(db_session, c, daily_streak=3)
    chests = await ls.closed_chests(db_session, c.id)
    assert len(chests) == 1 and chests[0].streak == 3 and chests[0].grade is None
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 0
    assert await ls.recent_history(db_session, c.id) == [], "закрытый ларец - не история"


async def test_open_owned_rewards_once(db_session, make_character) -> None:
    c = await make_character()
    await ls.grant_chest(db_session, c, daily_streak=1)
    chest, result = await ls.open_owned(db_session, c, None, random.Random(1))
    assert chest.status == "opened" and chest.grade == result.grade.id and result.lines
    with pytest.raises(ls.ChestGone):
        await ls.open_owned(db_session, c, chest.id, random.Random(1))
    with pytest.raises(ls.ChestGone):
        await ls.open_owned(db_session, c, None, random.Random(1))
    history = await ls.recent_history(db_session, c.id)
    assert len(history) == 1 and history[0].grade == result.grade.id


async def test_cannot_open_someone_elses_chest(db_session, make_character) -> None:
    owner = await make_character()
    thief = await make_character()
    chest = await ls.grant_chest(db_session, owner, daily_streak=1)
    with pytest.raises(ls.ChestGone):
        await ls.open_owned(db_session, thief, chest.id, random.Random(1))


async def test_roulette_lands_on_the_real_prize(db_session, make_character) -> None:
    c = await make_character()
    await ls.grant_chest(db_session, c, daily_streak=5)
    _chest, result = await ls.open_owned(db_session, c, None, random.Random(7))
    strip, win = ls.roulette_strip(result, 5, random.Random(8))
    assert len(strip) == ls.ROULETTE_LENGTH and win == ls.ROULETTE_WIN_INDEX
    assert strip[win]["grade"] == result.grade.id
    assert strip[win]["label"] == ", ".join(result.lines)
    assert all(card["icon"].startswith("chest:") and card["label"] for card in strip)


async def test_inventory_shows_chests_as_one_stack(db_session, make_character) -> None:
    from bot.miniapp_api import _full_inventory

    c = await make_character()
    for _ in range(3):
        await ls.grant_chest(db_session, c, daily_streak=1)
    stack = (await _full_inventory(db_session, c.id))["chests"]
    assert len(stack) == 1 and stack[0]["count"] == 3
    assert round(sum(g["chance"] for g in stack[0]["grades"])) == 100

