"""Турбоишак дня (2026-10-19): появление, бег, поимка, имя, маунт."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.economy import mount_config as mc
from game.economy import turbo_config as tc
from game.world import grid
from game.world import world_config as wc
from game.world import turbo_ishak as ti
from models import TurboIshakDay
from services import mount_service
from services import turbo_ishak_service as svc

# 15:00 по Москве - внутри окна появления.
NOON = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class Always(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__(1)
        self.value = value

    def random(self) -> float:
        return self.value


def test_mount_numbers_and_purple_epic() -> None:
    assert mount_service.seconds_per_cell(tc.MOUNT_ID) == 3.5
    assert mount_service.ambush_chance(tc.MOUNT_ID) == 0.65
    assert mount_service.mount_def(tc.MOUNT_ID).rarity == "epic"
    assert mc.RARITY_EMOJI["epic"] == "🟣"
    # Остальные маунты по-прежнему берут числа из редкости.
    assert mount_service.seconds_per_cell("ashen_steed") == mc.RARITY_SECONDS_PER_CELL["rare"]


def test_spawn_is_planned_inside_the_window() -> None:
    rng = random.Random(4)
    for _ in range(50):
        at = ti.plan_spawn(datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc), rng).astimezone(ti.MSK)
        assert tc.SPAWN_WINDOW_MSK[0] <= at.hour < tc.SPAWN_WINDOW_MSK[1]
    # Окно кончилось - сегодня его не будет.
    assert ti.plan_spawn(datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc), rng) is None


def test_cells_cover_the_whole_map_but_not_cities() -> None:
    cells = ti.free_cells()
    assert all(grid.city_region_at(*c) is None for c in cells)
    assert (0, 0) not in cells
    rings = {grid.monolith_distance(*c) for c in cells}
    assert min(rings) == 1 and max(rings) == wc.WORLD_RADIUS


def test_catch_chance_is_capped() -> None:
    assert ti.catch_chance("str", {"str": 1000, "agi": 1, "int": 1, "vit": 1, "wil": 1}) == tc.CATCH_MAX
    assert ti.catch_chance("str", {"str": 1, "agi": 100, "int": 100, "vit": 100, "wil": 100}) == tc.CATCH_MIN


def test_name_rules() -> None:
    assert ti.name_error("Алексей") is None
    assert ti.name_error("Пыхтун-Младший") is None
    assert ti.name_error("А") is not None
    assert ti.name_error("Очень-очень-длинное-имя") is not None
    assert ti.name_error("Ишак_1") is not None
    assert ti.clean_name("  Серый   Дым ") == "Серый Дым"


async def _run_until_active(db, rng) -> TurboIshakDay:
    await svc.tick(db, rng, NOON)
    day = await db.scalar(select(TurboIshakDay))
    day.spawn_at = NOON  # не ждать случайный момент окна
    await svc.tick(db, rng, NOON)
    assert day.status == svc.ACTIVE
    return day


async def test_day_lifecycle_spawn_move_gone(db_session) -> None:
    rng = random.Random(2)
    day = await _run_until_active(db_session, rng)
    assert ti.day_key(NOON) == day.day and (day.x, day.y) in set(ti.free_cells())
    # Одна строка на день: повторный тик второго не заводит.
    await svc.tick(db_session, rng, NOON)
    assert len((await db_session.scalars(select(TurboIshakDay))).all()) == 1

    moved = 0
    t = NOON
    for _ in range(30):
        t += timedelta(seconds=tc.MOVE_SECONDS[1] + 1)
        if t >= svc._aware(day.expires_at):
            break
        moved += sum(e.kind == "run" for e in await svc.tick(db_session, rng, t))
    assert moved > 0
    events = await svc.tick(db_session, rng, svc._aware(day.expires_at) + timedelta(seconds=1))
    assert [e.kind for e in events] == ["gone"] and day.status == svc.GONE


async def test_catch_and_name(db_session, make_character) -> None:
    day = await _run_until_active(db_session, random.Random(5))
    c = await make_character(level=30)
    c.pos_x, c.pos_y = day.x, day.y
    result = await svc.attempt(db_session, c, Always(0.0), NOON)
    assert result.outcome == "caught" and day.status == svc.CAUGHT and day.caught_by == c.id
    assert await svc.owns_turbo(db_session, c.id)

    peer = (await svc.awaiting_name(db_session))
    assert len(peer) == 1
    with pytest.raises(svc.TurboError):
        await svc.set_name(db_session, c, "Ишак_1")
    assert await svc.set_name(db_session, c, "  Алексей ") == "Алексей"
    owned = await mount_service.owned_mounts(db_session, c.id)
    assert [m.name for m in owned] == ["Турбоишак Алексей"]
    assert await svc.awaiting_name(db_session) == []


async def test_fail_makes_it_run_and_owner_cannot_try(db_session, make_character) -> None:
    day = await _run_until_active(db_session, random.Random(6))
    c = await make_character(level=30)
    c.pos_x, c.pos_y = day.x, day.y
    before = (day.x, day.y)
    result = await svc.attempt(db_session, c, Always(0.99), NOON)
    assert result.outcome == "ran" and (day.x, day.y) != before and day.status == svc.ACTIVE
    # Ушёл с клетки - подойти нельзя.
    # Сорвался и бежит: на бегу не схватить, даже если он ещё на твоей клетке.
    assert svc.is_running(day, NOON) and svc.current_cell(day, NOON) == before
    assert (await svc.attempt(db_session, c, Always(0.0), NOON)).outcome == "running"
    # Пробежал дальше - тебя на его клетке уже нет.
    later = NOON + timedelta(seconds=svc.step_seconds() * 1.5)
    assert svc.current_cell(day, later) != before
    assert (await svc.attempt(db_session, c, Always(0.0), later)).outcome == "not_here"

    owner = await make_character(level=30)
    await mount_service.grant(db_session, owner, tc.MOUNT_ID)
    owner.pos_x, owner.pos_y = day.x, day.y
    stopped = svc._arrival(day) + timedelta(seconds=1)
    assert (await svc.attempt(db_session, owner, Always(0.0), stopped)).outcome == "owned"


async def test_skip_name_keeps_plain_title(db_session, make_character) -> None:
    c = await make_character()
    await mount_service.grant(db_session, c, tc.MOUNT_ID)
    await svc.skip_name(db_session, c)
    assert [m.name for m in await mount_service.owned_mounts(db_session, c.id)] == ["Турбоишак"]
    assert await svc.awaiting_name(db_session) == []


async def test_run_goes_cell_by_cell_and_stops(db_session) -> None:
    """Бег по клеткам со скоростью маунта (2026-10-19): каждый шаг - в
    соседнюю клетку, добежал - стоит на цели и шлёт кнопки (arrive)."""
    rng = random.Random(9)
    day = await _run_until_active(db_session, rng)
    svc._start_run(day, rng, NOON)
    path, index, left = svc.run_view(day, NOON)
    assert index == 0 and path[0] == (day.from_x, day.from_y) and path[-1] == (day.x, day.y)
    assert 0 < left <= svc.step_seconds() == 3.5
    cells = [svc.current_cell(day, NOON + timedelta(seconds=i * svc.step_seconds())) for i in range(len(path))]
    assert cells == path
    for a, b in zip(cells, cells[1:]):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1
    arrival = NOON + timedelta(seconds=(len(path) - 1) * svc.step_seconds() + 1)
    events = await svc.tick(db_session, rng, arrival)
    assert [e.kind for e in events] == ["arrive"]
    assert not svc.is_running(day, arrival) and svc.current_cell(day, arrival) == (day.x, day.y)
