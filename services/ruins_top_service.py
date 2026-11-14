"""Топ руин (2026-11-13, владелец): глубина забегов за неделю.

Руины ходят группами, поэтому строка топа - забег, а не игрок: «33 этажа -
Еста, Ёста, Тихоня_Винни, Solar_Azure». Правила:

- Разделы: одиночки (в забеге был один игрок) и группы (2-5, считая
  изгнанных). Состав по ходу забега только уменьшается.
- В зачёт идёт этаж, хозяина которого убили (RuinMember.floors). Гибель
  группы не отнимает пройденное, изгнанный сохраняет этажи до изгнания.
- Игрок в топе один раз - лучшим забегом недели; при равенстве - тот, что
  раньше. Строка показывается, если она лучшая хотя бы для одного участника;
  остальные участники перечислены в ней бледно (best=False) - их место выше.
- Неделя - с понедельника 00:00 по Москве, забег относится к неделе, когда
  пройден его последний этаж. Итог в ночь на понедельник: ларцы рун тройке
  каждого раздела (в группе - каждому участнику, чьё это место) и титул на
  неделю - один, за лучшее место из двух разделов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from game import plural
from game.economy import ruins_config as rc
from models import Character, CharacterTitle, RuinMember, RuinWeek, RuinWeekResult

SOLO, GROUP = "solo", "group"
SECTIONS = (SOLO, GROUP)
MSK = ZoneInfo(rc.TOP_TZ)

#: Вкладки топов мини-аппа. Отдельно от leaderboard_service.BOARDS: те
#: несут венец первого места, а у топа руин награда своя - недельная.
BOARDS = {"ruins_solo": SOLO, "ruins_group": GROUP}
BOARD_TITLES = {"ruins_solo": "🏛 Руины: одиночки", "ruins_group": "🏛 Руины: группы"}

RULE = (
    "Глубина забега за неделю: этаж, хозяина которого вы убили. Если группа погибла, пройденные этажи "
    "всё равно засчитываются. Каждый игрок в топе один раз, своим лучшим забегом; при равенстве выше тот, "
    "кто дошёл раньше. Бледное имя в строке - у этого игрока место выше."
)
GROUP_RULE = "В группе награду за место получает каждый участник забега, у кого это лучшее место недели."


def prizes_text() -> str:
    parts = [
        f"{place} место - {plural.count(chests, 'ларец рун', 'ларца рун', 'ларцов рун')}"
        for place, (_, chests) in sorted(rc.TOP_PRIZES.items())
    ]
    return (
        "Итоги - в ночь на понедельник по Москве: " + ", ".join(parts)
        + ". Призёрам - титул на неделю, без бонусов."
    )

_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def week_start(now: datetime | None = None) -> date:
    """Понедельник текущей недели по Москве."""
    day = (now or _now()).astimezone(MSK).date()
    return day - timedelta(days=day.weekday())


def week_bounds(start: date) -> tuple[datetime, datetime]:
    begin = datetime.combine(start, time(0), tzinfo=MSK)
    return begin, begin + timedelta(days=7)


def week_label(start: date) -> str:
    """«9-15 ноября», через месяц - «30 ноября - 6 декабря»."""
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.day}-{end.day} {_MONTHS[end.month - 1]}"
    return f"{start.day} {_MONTHS[start.month - 1]} - {end.day} {_MONTHS[end.month - 1]}"


def floors_text(n: int) -> str:
    return plural.count(n, "этаж", "этажа", "этажей")


@dataclass
class Entry:
    """Один игрок в одном забеге."""

    member_id: int
    character_id: int
    run_id: int
    floors: int
    at: datetime
    size: int


@dataclass
class Member:
    character_id: int
    #: это лучший забег игрока - место его; False - игрок выше, в другой строке
    best: bool


@dataclass
class Row:
    rank: int
    run_id: int
    floors: int
    at: datetime
    size: int
    members: list[Member] = field(default_factory=list)


def _better(a: Entry, b: Entry) -> bool:
    """a лучше b: глубже, при равенстве - раньше."""
    return (a.floors, -a.at.timestamp(), -a.run_id) > (b.floors, -b.at.timestamp(), -b.run_id)


def build(entries: list[Entry], section: str) -> list[Row]:
    """Строки раздела по правилам из шапки модуля."""
    pool = [e for e in entries if (e.size == 1) == (section == SOLO)]
    best: dict[int, Entry] = {}
    for e in pool:
        cur = best.get(e.character_id)
        if cur is None or _better(e, cur):
            best[e.character_id] = e
    keys: dict[tuple[int, int], datetime] = {}
    for e in best.values():
        key = (e.run_id, e.floors)
        keys[key] = min(keys.get(key, e.at), e.at)
    rows = []
    for (run_id, floors), at in keys.items():
        inside = sorted(
            (e for e in pool if e.run_id == run_id and e.floors >= floors), key=lambda e: e.member_id,
        )
        members = [
            Member(e.character_id, (best[e.character_id].run_id, best[e.character_id].floors) == (run_id, floors))
            for e in inside
        ]
        rows.append(Row(0, run_id, floors, at, inside[0].size if inside else 1, members))
    rows.sort(key=lambda r: (-r.floors, r.at, r.run_id))
    for i, row in enumerate(rows, start=1):
        row.rank = i
    return rows


async def entries(db: AsyncSession, begin: datetime | None = None, end: datetime | None = None) -> list[Entry]:
    """Участия с пройденным этажом; begin/end - окно недели (None - всё время)."""
    size = (
        select(RuinMember.run_id.label("run_id"), func.count().label("n"))
        .group_by(RuinMember.run_id)
        .subquery()
    )
    query = (
        select(RuinMember.id, RuinMember.character_id, RuinMember.run_id, RuinMember.floors,
               RuinMember.floors_at, size.c.n)
        .join(size, size.c.run_id == RuinMember.run_id)
        .where(RuinMember.floors >= 1, RuinMember.floors_at.is_not(None))
    )
    if begin is not None:
        query = query.where(RuinMember.floors_at >= begin)
    if end is not None:
        query = query.where(RuinMember.floors_at < end)
    rows = (await db.execute(query)).all()
    return [Entry(mid, cid, run_id, floors, _aware(at), int(n)) for mid, cid, run_id, floors, at, n in rows]


async def week_rows(db: AsyncSession, section: str, now: datetime | None = None) -> tuple[date, list[Row]]:
    start = week_start(now)
    begin, end = week_bounds(start)
    return start, build(await entries(db, begin, end), section)


async def record(db: AsyncSession, section: str) -> Row | None:
    """Рекорд раздела за всё время - для строки над недельным топом."""
    rows = build(await entries(db), section)
    return rows[0] if rows else None


# --- Итог недели ------------------------------------------------------------------


@dataclass
class Place:
    section: str
    place: int
    floors: int
    chests: int


@dataclass
class Award:
    character_id: int
    places: list[Place]
    title_id: str
    #: титул надет сразу (раньше был без титула или с титулом руин)
    worn: bool

    @property
    def chests(self) -> int:
        return sum(p.chests for p in self.places)


async def close_week(db: AsyncSession, now: datetime | None = None) -> list[Award]:
    """Итог прошлой недели. Повторный вызов ничего не делает: строка недели
    ставится первой. Титулы прошлой недели снимаются всегда, даже если в
    этот раз призёров нет."""
    from services import lootbox_service, title_service

    start = week_start(now) - timedelta(days=7)
    try:
        async with db.begin_nested():
            db.add(RuinWeek(week_start=start))
            await db.flush()
    except IntegrityError:
        return []
    begin, end = week_bounds(start)
    week = await entries(db, begin, end)
    won: dict[int, list[tuple[str, Row]]] = {}
    for section in SECTIONS:
        for row in build(week, section)[:len(rc.TOP_PRIZES)]:
            for m in row.members:
                if m.best:
                    won.setdefault(m.character_id, []).append((section, row))

    await db.execute(update(Character).where(Character.active_title_id.in_(rc.TOP_TITLES))
                     .values(active_title_id=None).execution_options(synchronize_session=False))
    await db.execute(delete(CharacterTitle).where(CharacterTitle.title_id.in_(rc.TOP_TITLES)))

    awards: list[Award] = []
    for character_id, got in won.items():
        character = await db.get(Character, character_id)
        if character is None:
            continue
        await db.refresh(character, ["active_title_id"])
        got.sort(key=lambda sr: (sr[1].rank, SECTIONS.index(sr[0])))
        title_id = rc.TOP_PRIZES[got[0][1].rank][0]
        places = []
        for i, (section, row) in enumerate(got):
            chests = rc.TOP_PRIZES[row.rank][1]
            for _ in range(chests):
                await lootbox_service.grant_chest(db, character, character.daily_streak, lootbox_service.RUNE)
            db.add(RuinWeekResult(
                week_start=start, section=section, place=row.rank, character_id=character_id,
                run_id=row.run_id, floors=row.floors, chests=chests, title_id=title_id if i == 0 else None,
            ))
            places.append(Place(section, row.rank, row.floors, chests))
        await title_service.unlock(db, character, title_id)
        awards.append(Award(character_id, places, title_id, character.active_title_id == title_id))
    await db.flush()
    return awards


def award_text(award: Award) -> str:
    from services import title_service

    lines = ["🏛 Итоги недели в топе руин."]
    for p in award.places:
        lines.append(f"Среди {'одиночек' if p.section == SOLO else 'групп'}: {p.place} место, {floors_text(p.floors)}.")
    chests = plural.count(award.chests, "ларец рун", "ларца рун", "ларцов рун")
    lines.append(
        f"Награда: {chests} и титул «{title_service.name_of(award.title_id)}» до следующего понедельника."
    )
    if not award.worn:
        lines.append("Надеть его можно в мини-аппе: нажмите на титул в шапке.")
    return "\n".join(lines)


# --- Мои забеги (2026-11-14, владелец) ------------------------------------------

#: Сколько своих последних забегов показывать в топе руин.
MY_RUNS_LIMIT = 10


@dataclass
class MyRun:
    run_id: int
    floors: int
    reason: str | None
    bag: dict
    started_at: datetime
    finished_at: datetime | None
    party: list[int]


async def my_runs(db: AsyncSession, character_id: int, limit: int = MY_RUNS_LIMIT) -> list[MyRun]:
    """Последние законченные забеги игрока: засчитанные этажи (как в топе),
    чем кончилось, что было в мешке, кто шёл вместе."""
    from models import RuinRun

    rows = (await db.execute(
        select(RuinMember, RuinRun).join(RuinRun, RuinRun.id == RuinMember.run_id)
        .where(RuinMember.character_id == character_id, RuinRun.status != "active")
        .order_by(RuinRun.started_at.desc(), RuinRun.id.desc()).limit(limit)
    )).all()
    if not rows:
        return []
    run_ids = [run.id for _m, run in rows]
    party: dict[int, list[int]] = {}
    for run_id, cid in (await db.execute(
        select(RuinMember.run_id, RuinMember.character_id)
        .where(RuinMember.run_id.in_(run_ids)).order_by(RuinMember.id)
    )).all():
        party.setdefault(run_id, []).append(cid)
    return [
        MyRun(run.id, member.floors or 0, member.left_reason, member.bag or {},
              run.started_at, run.finished_at, party.get(run.id, [character_id]))
        for member, run in rows
    ]


def run_when(moment: datetime) -> str:
    local = moment.astimezone(MSK) if moment.tzinfo else moment.replace(tzinfo=timezone.utc).astimezone(MSK)
    return f"{local.day} {_MONTHS[local.month - 1]}, {local:%H:%M}"


def run_length(start: datetime, end: datetime | None) -> str | None:
    if end is None:
        return None
    minutes = max(1, round((end - start).total_seconds() / 60))
    hours, rest = divmod(minutes, 60)
    return f"{hours} ч {rest} мин" if hours else f"{rest} мин"
