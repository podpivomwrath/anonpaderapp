"""Турбоишак дня (2026-10-19): появление, бег по карте, поимка, имя.

Сервис не шлёт сообщений: tick() и attempt() возвращают, что случилось, а
говорит bot/handlers/turbo_ishak.py. Правила - game/world/turbo_ishak.py.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy import turbo_config as tc
from game.world import grid
from game.world import turbo_ishak as ti
from models import Character, CharacterMount, CharacterStats, TurboIshakDay
from services import death_service, mount_service

PLANNED, ACTIVE, CAUGHT, GONE = "planned", "active", "caught", "gone"


class TurboError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def active(db: AsyncSession) -> TurboIshakDay | None:
    return await db.scalar(select(TurboIshakDay).where(TurboIshakDay.status == ACTIVE))


async def owns_turbo(db: AsyncSession, character_id: int) -> bool:
    return await db.scalar(select(CharacterMount.id).where(
        CharacterMount.character_id == character_id, CharacterMount.mount_id == tc.MOUNT_ID,
    )) is not None


@dataclass
class TickEvent:
    #: spawn | run | arrive | gone
    kind: str
    day: TurboIshakDay


# --- Бег по клеткам ---
# Забег: от (from_x; from_y) к (x; y) по grid.line_path со скоростью маунта.
# Где он сейчас, считается от времени - как у маунта, без записи каждой клетки.


def step_seconds() -> float:
    return mount_service.seconds_per_cell(tc.MOUNT_ID)


def run_path(day: TurboIshakDay) -> list[tuple[int, int]]:
    """Клетки забега без стартовой."""
    return grid.line_path(day.from_x, day.from_y, day.x, day.y)


def _arrival(day: TurboIshakDay) -> datetime:
    return _aware(day.run_started_at) + timedelta(seconds=len(run_path(day)) * step_seconds())


def is_running(day: TurboIshakDay, now: datetime | None = None) -> bool:
    return day.run_started_at is not None and (now or _now()) < _arrival(day)


def run_view(day: TurboIshakDay, now: datetime | None = None) -> tuple[list[tuple[int, int]], int, float] | None:
    """(путь со стартовой клеткой, индекс текущей клетки в нём, секунд до
    следующей) - для карты; None - стоит."""
    now = now or _now()
    if not is_running(day, now):
        return None
    path = [(day.from_x, day.from_y), *run_path(day)]
    step = step_seconds()
    elapsed = max((now - _aware(day.run_started_at)).total_seconds(), 0.0)
    index = min(int(elapsed // step), len(path) - 1)
    return path, index, step - elapsed % step


def current_cell(day: TurboIshakDay, now: datetime | None = None) -> tuple[int, int]:
    view = run_view(day, now)
    if view is None:
        return day.x, day.y
    path, index, _left = view
    return path[index]


def _start_run(day: TurboIshakDay, rng: random.Random, now: datetime) -> None:
    """Сорваться с места и бежать на случайную клетку карты."""
    day.from_x, day.from_y = current_cell(day, now)
    day.x, day.y = ti.pick_cell(rng, avoid=(day.from_x, day.from_y))
    day.run_started_at = now
    day.next_move_at = _arrival(day) + timedelta(seconds=ti.next_move_delay(rng))


async def tick(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> list[TickEvent]:
    """Раз в несколько секунд: запланировать день, выпустить, перегнать,
    закончить. Возвращает, что изменилось (для кнопок тем, к кому прибежал)."""
    now = now or _now()
    events: list[TickEvent] = []
    key = ti.day_key(now)
    today = await db.scalar(select(TurboIshakDay).where(TurboIshakDay.day == key))
    if today is None:
        spawn_at = ti.plan_spawn(now, rng)
        if spawn_at is not None:
            db.add(TurboIshakDay(day=key, status=PLANNED, spawn_at=spawn_at))
            await db.flush()
    rows = (await db.scalars(
        select(TurboIshakDay).where(TurboIshakDay.status.in_((PLANNED, ACTIVE)))
        .with_for_update().execution_options(populate_existing=True)
    )).all()
    for day in rows:
        if day.status == PLANNED:
            if _aware(day.spawn_at) > now:
                continue
            if day.day != key:
                day.status = GONE  # не успел выйти до полуночи (бот лежал) - день пропал
                continue
            day.x, day.y = ti.pick_cell(rng)
            day.run_started_at = None
            day.status = ACTIVE
            day.expires_at = now + timedelta(minutes=tc.LIFETIME_MINUTES)
            day.next_move_at = now + timedelta(seconds=ti.next_move_delay(rng))
            events.append(TickEvent("spawn", day))
        elif _aware(day.expires_at) <= now:
            day.status = GONE
            events.append(TickEvent("gone", day))
        elif day.run_started_at is not None:
            if now >= _arrival(day):
                day.run_started_at = None  # добежал и встал на (x; y)
                events.append(TickEvent("arrive", day))
        elif _aware(day.next_move_at) <= now:
            if rng.random() < tc.STAY_CHANCE:
                day.next_move_at = now + timedelta(seconds=ti.next_move_delay(rng))
            else:
                _start_run(day, rng, now)
                events.append(TickEvent("run", day))
    await db.flush()
    return events


def can_approach_reason(character: Character, day: TurboIshakDay | None, owns: bool, now: datetime) -> str | None:
    """Почему нельзя подойти (None - можно)."""
    if day is None or day.status != ACTIVE:
        return "gone"
    if is_running(day, now):
        return "running" if (character.pos_x, character.pos_y) == current_cell(day, now) else "not_here"
    if (character.pos_x, character.pos_y) != (day.x, day.y):
        return "not_here"
    if owns:
        return "owned"
    if death_service.is_dead(character, now):
        return "dead"
    return None


async def catch_chance(db: AsyncSession, character: Character) -> tuple[str, float]:
    """(основной стат, шанс) - для подписи кнопки и броска."""
    from services import scene_event_service

    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    totals = await scene_event_service.total_stats(db, character, stats)
    stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    return stat, ti.catch_chance(stat, totals)


@dataclass
class Attempt:
    #: caught | ran | gone | not_here | running | owned | dead
    outcome: str
    chance: float = 0.0
    stat: str = ""


async def attempt(db: AsyncSession, character: Character, rng: random.Random, now: datetime | None = None) -> Attempt:
    """«Подойти»: проверка основного стата. Поймал - маунт твой, ишак уходит
    с карты до завтра. Нет - убегает на другую клетку."""
    now = now or _now()
    day = await db.scalar(
        select(TurboIshakDay).where(TurboIshakDay.status == ACTIVE)
        .with_for_update().execution_options(populate_existing=True)
    )
    reason = can_approach_reason(character, day, await owns_turbo(db, character.id), now)
    if reason is not None:
        return Attempt(reason)
    stat, chance = await catch_chance(db, character)
    if rng.random() < chance:
        await mount_service.grant(db, character, tc.MOUNT_ID)
        day.status = CAUGHT
        day.caught_by = character.id
        day.caught_at = now
        await db.flush()
        return Attempt("caught", chance, stat)
    _start_run(day, rng, now)
    await db.flush()
    return Attempt("ran", chance, stat)


# --- Имя ----------------------------------------------------------------------


async def _turbo_row(db: AsyncSession, character_id: int) -> CharacterMount | None:
    return await db.scalar(select(CharacterMount).where(
        CharacterMount.character_id == character_id, CharacterMount.mount_id == tc.MOUNT_ID,
    ))


async def set_name(db: AsyncSession, character: Character, raw) -> str:
    """Дать имя пойманному ишаку. Возвращает имя или бросает TurboError."""
    from services import onboarding_service

    row = await _turbo_row(db, character.id)
    if row is None:
        raise TurboError("Турбоишака у тебя нет.")
    name = ti.clean_name(raw)
    error = ti.name_error(name)
    if error is None and onboarding_service.contains_banned_word(name):
        error = "Такое имя не пройдёт - выбери другое."
    if error is not None:
        raise TurboError(error)
    row.nickname = name
    await db.flush()
    return name


async def skip_name(db: AsyncSession, character: Character) -> None:
    row = await _turbo_row(db, character.id)
    if row is not None and row.nickname is None:
        row.nickname = ""
        await db.flush()


async def awaiting_name(db: AsyncSession) -> list[int]:
    """vk_id тех, кто поймал ишака и ещё не ответил, как его звать, - бот
    ждёт имя и после перезапуска."""
    from models import User

    rows = await db.execute(
        select(User.vk_id).join(Character, Character.user_id == User.id)
        .join(CharacterMount, CharacterMount.character_id == Character.id)
        .where(CharacterMount.mount_id == tc.MOUNT_ID, CharacterMount.nickname.is_(None))
    )
    return [vk for vk in rows.scalars().all() if vk is not None]


async def peers_on_cell(db: AsyncSession, x: int, y: int, now: datetime | None = None) -> list[tuple[int, Character]]:
    """Кто стоит на клетке и недавно что-то делал - им ишак прибежал сам."""
    from models import User

    now = now or _now()
    since = now - timedelta(minutes=tc.NEARBY_ACTIVE_MINUTES)
    rows = await db.execute(
        select(User.vk_id, Character).join(Character, Character.user_id == User.id).where(
            Character.pos_x == x, Character.pos_y == y, Character.creation_state.is_(None),
            Character.last_active_at >= since,
        )
    )
    return [(vk, c) for vk, c in rows.all() if vk is not None]


async def news_recipients(db: AsyncSession, now: datetime | None = None, hours: int = tc.NEWS_ACTIVE_HOURS) -> list[int]:
    from models import User

    since = (now or _now()) - timedelta(hours=hours)
    rows = await db.execute(
        select(User.vk_id).join(Character, Character.user_id == User.id)
        .where(Character.creation_state.is_(None), Character.last_active_at >= since)
    )
    return [vk for vk in rows.scalars().all() if vk is not None]
