"""Рейтинг PvP - PTS (2026-10-13)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from models import Character
from services import pts_service


def _c(pts: int, level: int = 30, cid: int = 1):
    return SimpleNamespace(id=cid, pts=pts, level=level)


def test_equal_gives_twenty() -> None:
    assert round(pts_service.pair_points(_c(1000), _c(1000)).points) == 20


def test_favourite_gets_little_and_nothing_past_cutoff() -> None:
    assert round(pts_service.pair_points(_c(1200), _c(1000)).points) == 10
    over = pts_service.pair_points(_c(1300), _c(1000))
    assert over.points == 0 and over.reason == pts_service.NO_GAP


def test_underdog_gets_a_lot_with_upset_bonus() -> None:
    # -200: ~30 по Эло, x1.5 за победу над тем, кто выше на 200+
    assert round(pts_service.pair_points(_c(1000), _c(1200)).points) == 46
    assert round(pts_service.pair_points(_c(1000), _c(1400)).points) > 50


def test_no_points_for_victim_five_levels_lower() -> None:
    res = pts_service.pair_points(_c(1000, level=30), _c(1000, level=25))
    assert res.points == 0 and res.reason == pts_service.NO_LEVEL
    assert pts_service.pair_points(_c(1000, level=30), _c(1000, level=26)).points > 0


def test_low_level_above_in_rating_is_fair_game() -> None:
    """2026-10-23: младший, обогнавший старшего по PTS, не прячется за
    разницей уровней - очки обычные, без надбавки за сильнейшего."""
    res = pts_service.pair_points(_c(1000, level=50), _c(1300, level=20))
    assert res.reason is None and round(res.points) == round(40 * (1 - 1 / (1 + 10 ** (300 / 400))))
    # Ниже по рейтингу - по-прежнему ничего.
    assert pts_service.pair_points(_c(1300, level=50), _c(1000, level=20)).reason == pts_service.NO_LEVEL


def test_mass_branded_low_level_victim_counts() -> None:
    from datetime import datetime, timezone

    a = SimpleNamespace(id=1, pts=1000, level=50, pk_marks=0, pk_marks_at=None)
    v = SimpleNamespace(id=2, pts=1000, level=20, pk_marks=3, pk_marks_at=datetime.now(timezone.utc))
    deltas = pts_service.apply_mass({1: a, 2: v}, [2], {(1, 2): 100}, {1: 0, 2: 1})
    assert deltas == {1: 20, 2: -20}


def test_duel_moves_points_both_ways() -> None:
    w, l = _c(1000), _c(1000, cid=2)
    delta, reason = pts_service.apply_duel(w, l)
    assert delta == 20 and reason is None and (w.pts, l.pts) == (1020, 980)


def test_farming_one_victim_dries_up() -> None:
    """Защита от накрутки - сама формула: из одного соперника ~150 PTS."""
    w, l = _c(1000), _c(1000, cid=2)
    for _ in range(200):
        pts_service.apply_duel(w, l)
    assert w.pts - 1000 <= 160 and w.pts - l.pts < 330


def test_mass_shares_by_damage() -> None:
    a, b, v = _c(1000, cid=1), _c(1000, cid=2), _c(1000, cid=3)
    chars = {1: a, 2: b, 3: v}
    deltas = pts_service.apply_mass(chars, [3], {(1, 3): 300, (2, 3): 100}, {1: 0, 2: 0, 3: 1})
    assert deltas == {1: 15, 2: 5, 3: -20}
    assert (a.pts, b.pts, v.pts) == (1015, 1005, 980)


async def test_season_rollover_compresses_to_start(db_session, make_character) -> None:
    hi = await make_character(level=30)
    lo = await make_character(level=30)
    hi.pts, hi.pts_season = 1400, "2026-09"
    lo.pts, lo.pts_season = 800, "2026-09"
    await db_session.flush()
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    assert await pts_service.season_rollover(db_session, now) >= 2
    rows = dict((await db_session.execute(
        select(Character.id, Character.pts).where(Character.id.in_([hi.id, lo.id]))
    )).all())
    assert rows[hi.id] == 1200 and rows[lo.id] == 900
    # повторно в том же сезоне - ничего не трогает
    assert await pts_service.season_rollover(db_session, now) == 0


def test_rank_names() -> None:
    assert pts_service.rank_name(850) == "Пепел"
    assert pts_service.rank_name(1000) == "Сталь"
    assert pts_service.rank_name(1550) == "Монолит"
