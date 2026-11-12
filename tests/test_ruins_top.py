"""Топ руин (2026-11-13, владелец): строка - забег, игрок в топе один раз
своим лучшим забегом недели, разделы одиночек и групп, итог недели - ларцы
рун тройке и титул на неделю."""

import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from game.economy import ruins_config as rc
from models import CharacterLootbox, CharacterTitle, RuinMember, RuinRun, RuinWeekResult
from services import lootbox_service, ruins_service
from services import ruins_top_service as rts

# Среда 11 ноября 2026, полдень по Москве.
WED = datetime(2026, 11, 11, 9, tzinfo=timezone.utc)
# Понедельник 16 ноября, 00:00 по Москве.
NEXT_MON = datetime(2026, 11, 15, 21, 0, 30, tzinfo=timezone.utc)


def E(member_id, character_id, run_id, floors, minute, size):
    return rts.Entry(member_id, character_id, run_id, floors, WED + timedelta(minutes=minute), size)


def test_week_bounds_and_label() -> None:
    assert rts.week_start(WED) == date(2026, 11, 9)
    # Воскресенье 23:59 по Москве - ещё прошлая неделя.
    assert rts.week_start(datetime(2026, 11, 15, 20, 59, tzinfo=timezone.utc)) == date(2026, 11, 9)
    assert rts.week_start(NEXT_MON) == date(2026, 11, 16)
    assert rts.week_label(date(2026, 11, 9)) == "9-15 ноября"
    assert rts.week_label(date(2026, 11, 30)) == "30 ноября - 6 декабря"
    assert rts.floors_text(33) == "33 этажа" and rts.floors_text(11) == "11 этажей"


def test_solo_and_group_split() -> None:
    entries = [E(1, 1, 10, 17, 0, 1), E(2, 2, 11, 33, 0, 4), E(3, 3, 11, 33, 0, 4)]
    solo = rts.build(entries, rts.SOLO)
    group = rts.build(entries, rts.GROUP)
    assert [(r.floors, [m.character_id for m in r.members]) for r in solo] == [(17, [1])]
    assert [(r.floors, [m.character_id for m in r.members]) for r in group] == [(33, [2, 3])]


def test_player_in_two_groups_counts_once() -> None:
    """Еста: 33 с одной группой (её место), 20 - с другой; во второй строке
    она бледная, а строка есть ради остальных."""
    entries = [
        E(1, 1, 10, 33, 0, 4), E(2, 2, 10, 33, 0, 4),
        E(3, 1, 11, 20, 5, 3), E(4, 3, 11, 20, 5, 3), E(5, 4, 11, 20, 5, 3),
    ]
    rows = rts.build(entries, rts.GROUP)
    assert [r.floors for r in rows] == [33, 20]
    assert [(m.character_id, m.best) for m in rows[1].members] == [(1, False), (3, True), (4, True)]


def test_run_hidden_when_nobody_has_it_as_best() -> None:
    entries = [
        E(1, 1, 10, 33, 0, 2), E(2, 2, 10, 33, 0, 2),
        E(3, 1, 11, 30, 5, 2), E(4, 2, 11, 30, 5, 2),
    ]
    assert [r.floors for r in rts.build(entries, rts.GROUP)] == [33]


def test_tie_goes_to_earlier_and_kicked_keeps_own_floors() -> None:
    entries = [
        E(1, 1, 10, 12, 30, 1), E(2, 2, 11, 12, 10, 1),
        # Тройка: третьего выгнали после 5 этажа.
        E(3, 3, 12, 20, 0, 3), E(4, 4, 12, 20, 0, 3), E(5, 5, 12, 5, 0, 3),
    ]
    solo = rts.build(entries, rts.SOLO)
    assert [r.members[0].character_id for r in solo] == [2, 1]
    group = rts.build(entries, rts.GROUP)
    assert [(r.floors, [m.character_id for m in r.members]) for r in group] == [(20, [3, 4]), (5, [3, 4, 5])]
    assert [m.best for m in group[1].members] == [False, False, True]


async def test_boss_kill_records_floor_for_everyone_inside(db_session, make_character) -> None:
    a, b = await _party(make_character, 2)
    run = await ruins_service.start(db_session, a, [a, b], random.Random(1))
    run.pos = run.layout["boss"]
    await ruins_service.room_won(db_session, run, {a.id: 100, b.id: 0}, {}, random.Random(1))
    for m in await ruins_service.members(db_session, run.id):
        assert m.floors == 1 and m.floors_at is not None


async def test_close_week_rewards_and_titles(db_session, make_character) -> None:
    solo1, solo2, g1, g2 = [await make_character(level=60) for _ in range(4)]
    await _member(db_session, solo1, floors=17, at=WED)
    await _member(db_session, solo2, floors=9, at=WED)
    run = await _member(db_session, g1, floors=33, at=WED)
    await _member(db_session, g2, floors=33, at=WED, run=run)
    # Тот же solo1 - вторым в группе: два места, ларцы за оба, титул один.
    other = await _member(db_session, g1, floors=5, at=WED + timedelta(hours=1))
    await _member(db_session, solo1, floors=5, at=WED + timedelta(hours=1), run=other)
    # Прошлая неделя в итог не идёт.
    await _member(db_session, solo2, floors=50, at=WED - timedelta(days=7))
    await db_session.flush()

    awards = {a.character_id: a for a in await rts.close_week(db_session, NEXT_MON)}
    assert await rts.close_week(db_session, NEXT_MON) == []

    assert set(awards) == {solo1.id, solo2.id, g1.id, g2.id}
    assert [(p.section, p.place) for p in awards[solo1.id].places] == [("solo", 1), ("group", 2)]
    assert awards[solo1.id].chests == 15 and awards[solo1.id].title_id == "ruins_first"
    assert awards[g1.id].chests == 10 and awards[g2.id].chests == 10
    assert awards[solo2.id].chests == 5 and awards[solo2.id].title_id == "ruins_second"
    chests = (await db_session.scalars(select(CharacterLootbox).where(
        CharacterLootbox.character_id == solo1.id))).all()
    assert len(chests) == 15 and {c.kind for c in chests} == {lootbox_service.RUNE}
    assert solo1.active_title_id == "ruins_first"
    results = (await db_session.scalars(select(RuinWeekResult).where(
        RuinWeekResult.character_id == solo1.id))).all()
    assert sorted((r.section, r.title_id) for r in results) == [("group", None), ("solo", "ruins_first")]
    assert "15 ларцов рун" in rts.award_text(awards[solo1.id])

    # Через неделю без забегов титулы снимаются.
    assert await rts.close_week(db_session, NEXT_MON + timedelta(days=7)) == []
    await db_session.refresh(solo1)
    assert solo1.active_title_id is None
    left = (await db_session.scalars(select(CharacterTitle).where(
        CharacterTitle.title_id.in_(rc.TOP_TITLES)))).all()
    assert left == []


async def test_weekly_title_does_not_replace_another_title(db_session, make_character) -> None:
    c = await make_character(level=60)
    c.active_title_id = "relentless"
    await _member(db_session, c, floors=3, at=WED)
    (award,) = await rts.close_week(db_session, NEXT_MON)
    assert c.active_title_id == "relentless" and not award.worn
    assert "нажмите на титул" in rts.award_text(award)


async def _party(make_character, n):
    chars = []
    for _ in range(n):
        c = await make_character(level=60)
        c.pos_x, c.pos_y = rc.ENTRY_CELL
        chars.append(c)
    return chars


async def _member(db, character, *, floors, at, run=None):
    if run is None:
        run = RuinRun(status="done", outcome="exited", leader_id=character.id, floor=floors, layout={},
                      pos=0, visited=[], cleared=[], phase="cleared", deepest=floors, gifts=[], extra={})
        db.add(run)
        await db.flush()
    db.add(RuinMember(run_id=run.id, character_id=character.id, active=False, hp=1, dead=False,
                      consumables_used=0, bag={}, floors=floors, floors_at=at))
    await db.flush()
    return run
