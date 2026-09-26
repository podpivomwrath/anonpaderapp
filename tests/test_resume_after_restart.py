"""Занятия, оборванные перезапуском бота (патч 98).

Деплой стирал отложенные задачи планировщика и отметки «занят», а у игрока на
экране оставалась клавиатура ожидания без единой кнопки. Переход, исследование
и отдых не заканчивались никогда.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bot import pending_activity
from bot.handlers import world

ROOT = Path(__file__).resolve().parent.parent


class FakeRedis:
    """Ровно то, чем пользуется pending_activity."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)

    async def scan_iter(self, match):
        prefix = match.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[int, float] = {}

    def schedule(self, peer_id, delay):
        self.jobs[peer_id] = delay


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(pending_activity, "_redis", fake)
    return fake


# --- Хранилище ---------------------------------------------------------------


async def test_remembered_activity_survives_and_counts_down(redis) -> None:
    await pending_activity.remember("rest", 42, 60)

    ((kind, peer, left),) = await pending_activity.pending()

    assert (kind, peer) == ("rest", 42)
    # Срок хранится с точностью до миллисекунды, поэтому «осталось» может
    # оказаться на доли миллисекунды больше заказанного - это не ошибка.
    assert 55 < left <= 60.01


async def test_overdue_activity_is_due_now_not_negative(redis) -> None:
    """Деплой затянулся дольше самого занятия - завершить сразу, а не
    планировать в прошлое."""
    past = datetime.now(timezone.utc).timestamp() - 300
    redis.data["pending:explore:7"] = f"{past:.3f}"

    ((_, _, left),) = await pending_activity.pending()

    assert left == 0.0


async def test_forgotten_activity_is_gone(redis) -> None:
    await pending_activity.remember("explore", 5, 30)
    await pending_activity.forget("explore", 5)
    assert await pending_activity.pending() == []


async def test_without_redis_everything_is_a_quiet_no_op(monkeypatch) -> None:
    """Тесты и локальный запуск идут без Redis - занятия работают как
    раньше, просто не переживают перезапуск."""
    monkeypatch.setattr(pending_activity, "_redis", None)
    await pending_activity.remember("rest", 1, 10)
    await pending_activity.forget("rest", 1)
    assert await pending_activity.pending() == []


# --- Возобновление -------------------------------------------------------------


@pytest.fixture
async def wired_world(monkeypatch, redis):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    schedulers = {"travel": FakeScheduler(), "explore": FakeScheduler(), "rest": FakeScheduler()}
    monkeypatch.setattr(world, "get_session_factory", lambda: factory)
    monkeypatch.setattr(world, "_travel_scheduler", schedulers["travel"])
    monkeypatch.setattr(world, "_explore_scheduler", schedulers["explore"])
    monkeypatch.setattr(world, "_rest_scheduler", schedulers["rest"])
    monkeypatch.setattr(world, "_exploring", set())
    monkeypatch.setattr(world, "_resting", set())
    yield factory, schedulers
    await engine.dispose()


async def _walker(factory, vk_id: int, arrives_in: float) -> None:
    from models import Character, User

    async with factory() as db:
        user = User(vk_id=vk_id)
        db.add(user)
        await db.flush()
        db.add(Character(
            user_id=user.id, name=f"Путник{vk_id}", base_class="warrior", level=10,
            pos_x=1, pos_y=1, travel_target_x=2, travel_target_y=1,
            travel_arrives_at=datetime.now(timezone.utc) + timedelta(seconds=arrives_in),
        ))
        await db.commit()


async def test_walk_in_progress_gets_its_arrival_back(wired_world) -> None:
    factory, schedulers = wired_world
    await _walker(factory, 3001, arrives_in=6)

    resumed = await world.resume_after_restart()

    assert resumed["travel"] == 1
    assert 0 < schedulers["travel"].jobs[3001] <= 6


async def test_walk_that_should_have_ended_arrives_at_once(wired_world) -> None:
    factory, schedulers = wired_world
    await _walker(factory, 3002, arrives_in=-120)

    await world.resume_after_restart()

    assert schedulers["travel"].jobs[3002] == 0.0


async def test_rest_and_explore_are_put_back_where_they_were(wired_world) -> None:
    """Колбэк отдыха выходит молча, если игрока нет в _resting, - поэтому
    мало перезапланировать задачу, надо вернуть и отметку."""
    _factory, schedulers = wired_world
    await pending_activity.remember("rest", 11, 40)
    await pending_activity.remember("explore", 12, 20)

    resumed = await world.resume_after_restart()

    assert resumed == {"travel": 0, "explore": 1, "rest": 1}
    assert 11 in world._resting and 11 in schedulers["rest"].jobs
    assert 12 in world._exploring and 12 in schedulers["explore"].jobs


# --- Прерванное не воскресает --------------------------------------------------


def test_every_interruption_also_clears_the_redis_mark() -> None:
    """Каждое место, где занятие снимается из памяти, обязано снять и запись
    в Redis. Иначе прерванный отдых воскреснет после следующего деплоя и
    вылечит бесплатно, а сброшенное через /застрял исследование - вернётся.
    """
    code = re.sub(r"#[^\n]*", "", (ROOT / "bot" / "handlers" / "world.py").read_text(encoding="utf-8"))
    for kind, registry in (("explore", "_exploring"), ("rest", "_resting")):
        dropped = len(re.findall(rf"{registry}\.discard\(", code))
        forgotten = len(re.findall(rf'pending_activity\.forget\("{kind}"', code))
        assert dropped == forgotten, (
            f"{registry}: снимается в {dropped} местах, а запись в Redis - в {forgotten}"
        )
        started = len(re.findall(rf"{registry}\.add\(", code))
        remembered = len(re.findall(rf'pending_activity\.remember\("{kind}"', code))
        # +1: resume_after_restart возвращает отметку, но запись там уже есть.
        assert remembered == started - 1, (
            f"{registry}: начинается в {started - 1} местах, запоминается в {remembered}"
        )
