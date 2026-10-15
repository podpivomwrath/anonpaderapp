"""Вкладка «Доска»: розыск и сезон (bot/miniapp_board_api.py)."""

from datetime import datetime, timezone

from bot import miniapp_board_api as board
from services import pk_service

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


async def test_wanted_lists_branded_with_bounty(db_session, make_character):
    killer = await make_character(level=30, farm=1000)
    weak = await make_character(level=10)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    await pk_service.on_pvp_kill(db_session, killer, weak, NOW)
    rows = await board._wanted(db_session, NOW)
    assert [(r["name"], r["marks"], r["bounty"]) for r in rows] == [(killer.name, 2, 100)]
    assert rows[0]["next_decay_min"] == 300


def test_season():
    season = board._season(NOW)
    assert season["name"] == "Октябрь 2026" and season["days_left"] == 16


async def test_rank_of_matches_board_on_full_tie(db_session, make_character):
    from services import leaderboard_service, pvp_service

    a = await make_character(level=20)
    b = await make_character(level=20)
    for c in (a, b):
        c.pts, c.pvp_wins, c.pvp_losses = 1000, 1, 0
    await db_session.flush()
    rows = await leaderboard_service.board(db_session, leaderboard_service.BOARD_PVP, limit=10)
    order = [r.character_id for r in rows]
    for c in (a, b):
        assert await pvp_service.rank_of(db_session, c) == order.index(c.id) + 1
