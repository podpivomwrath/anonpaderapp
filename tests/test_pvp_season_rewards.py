"""Награды сезона PvP (2026-10-30, владелец): пятёрка лучших по PTS среди
тех, кто провёл SEASON_MIN_FIGHTS боёв; титул на следующий сезон и
самоцветы; прошлые сезонные титулы снимаются; итог выдаётся один раз."""

from datetime import datetime, timezone

from sqlalchemy import select

from game.economy import pts_config as pc
from models import Character, CharacterTitle, PvpBattle, PvpSeasonResult
from services import pts_service, title_service, wallet_service

NOV = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
OCT_DAY = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


async def _fighters(db, make_character, pts_list, fights=pc.SEASON_MIN_FIGHTS):
    chars = []
    for pts in pts_list:
        c = await make_character(level=40)
        c.pts, c.pts_season = pts, "2026-10"
        chars.append(c)
    await db.flush()
    for c in chars:
        for _ in range(fights):
            db.add(PvpBattle(battle_type="duel", participant_ids=[c.id], winner_ids=[c.id], started_at=OCT_DAY))
    await db.flush()
    return chars


async def _titles(db, cid):
    return set((await db.scalars(select(CharacterTitle.title_id).where(CharacterTitle.character_id == cid))).all())


async def test_top_five_get_titles_and_gems_once(db_session, make_character) -> None:
    chars = await _fighters(db_session, make_character, [1400, 1300, 1200, 1150, 1100, 1050])
    lazy = await make_character(level=40)
    lazy.pts, lazy.pts_season = 1900, "2026-10"  # рейтинг высокий, боёв нет
    await db_session.flush()
    gems_before = {c.id: (await wallet_service.get_wallet(db_session, c.id)).donate_currency for c in chars}

    await pts_service.season_rollover(db_session, NOV)
    results = (await db_session.scalars(select(PvpSeasonResult).order_by(PvpSeasonResult.place))).all()
    assert [r.character_id for r in results] == [c.id for c in chars[:5]]
    assert [r.title_id for r in results] == ["pvp_first", "pvp_crimson", "pvp_crimson", "pvp_steel", "pvp_steel"]
    for c, gems in zip(chars[:5], (1000, 500, 500, 150, 150)):
        wallet = await wallet_service.get_wallet(db_session, c.id)
        assert wallet.donate_currency - gems_before[c.id] == gems
    assert await _titles(db_session, chars[0].id) == {"pvp_first"}
    assert chars[0].active_title_id == "pvp_first"
    assert not await _titles(db_session, lazy.id) and not await _titles(db_session, chars[5].id)

    # Повторно - ничего: сезон уже сжат и закрыт.
    assert await pts_service.season_close(db_session, NOV) == []
    medals = await pts_service.season_medals(db_session, NOV)
    assert medals == {chars[0].id: "🥇", chars[1].id: "🥈", chars[2].id: "🥉"}


async def test_titles_are_taken_from_last_season_winners(db_session, make_character) -> None:
    old = await make_character(level=40)
    await title_service.unlock(db_session, old, "pvp_first")
    old.active_title_id = "pvp_first"
    old.pts, old.pts_season = 1000, "2026-10"
    new = (await _fighters(db_session, make_character, [1300]))[0]

    await pts_service.season_rollover(db_session, NOV)
    await db_session.refresh(old)
    assert not await _titles(db_session, old.id) and old.active_title_id is None
    assert await _titles(db_session, new.id) == {"pvp_first"}


async def test_no_qualified_players_no_results(db_session, make_character) -> None:
    await _fighters(db_session, make_character, [1300], fights=pc.SEASON_MIN_FIGHTS - 1)
    await pts_service.season_rollover(db_session, NOV)
    assert not (await db_session.scalars(select(PvpSeasonResult))).all()
    rows = (await db_session.scalars(select(Character.pts_season))).all()
    assert set(rows) == {"2026-11"}


def test_season_bounds_cross_year() -> None:
    start, end = pts_service.season_bounds("2026-12")
    assert (start.year, start.month, end.year, end.month) == (2026, 12, 2027, 1)


async def test_recap_shown_once_and_not_to_newcomers(db_session, make_character) -> None:
    winner = (await _fighters(db_session, make_character, [1300]))[0]
    newbie = await make_character(level=5)
    newbie.pts_season = None
    await db_session.flush()
    await pts_service.season_rollover(db_session, NOV)
    await db_session.refresh(winner)
    await db_session.refresh(newbie)

    recap = await pts_service.season_recap(db_session, winner, NOV)
    assert recap["season"] == "2026-10" and recap["next"] == "2026-11"
    assert recap["me"]["place"] == 1 and recap["me"]["pts_was"] == 1300 and recap["me"]["pts_now"] == 1150
    assert recap["top"][0]["name"] == winner.name
    assert await pts_service.season_recap(db_session, newbie, NOV) is None

    winner.pvp_season_seen = "2026-11"
    assert await pts_service.season_recap(db_session, winner, NOV) is None
