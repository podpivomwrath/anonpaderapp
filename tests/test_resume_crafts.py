"""Рыбалка и добыча после перезапуска бота (2026-10-12).

Заброс и добыча лежат в базе, а таймеры «клюёт!» и «руда добыта» жили только
в памяти: после деплоя поклёвка не приходила, руда не выдавалась. Теперь при
запуске таймеры заводятся заново; поклёвка, чьё окно подсечки съел перезапуск,
приходит снова с полным окном."""

from datetime import datetime, timedelta, timezone

import pytest

from bot.handlers import fishing, mining
from game.economy import fishing_config as fc


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[int, float] = {}

    def schedule(self, peer_id, delay):
        self.jobs[peer_id] = delay


@pytest.fixture
async def factory(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(fishing, "get_session_factory", lambda: f)
    monkeypatch.setattr(mining, "get_session_factory", lambda: f)
    yield f
    await engine.dispose()


async def _player(f, vk_id: int, **fields):
    from models import Character, User

    async with f() as db:
        user = User(vk_id=vk_id)
        db.add(user)
        await db.flush()
        character = Character(user_id=user.id, name=f"Рыбак{vk_id}", base_class="rogue", level=10, **fields)
        db.add(character)
        await db.commit()
        return character.id


async def test_bite_ahead_is_rescheduled_on_its_time(factory, monkeypatch) -> None:
    sched = FakeScheduler()
    monkeypatch.setattr(fishing, "_bite_scheduler", sched)
    now = datetime.now(timezone.utc)
    await _player(factory, 11, fishing_cast_at=now, fishing_bite_at=now + timedelta(seconds=20),
                  fishing_pending_fish="perch", fishing_pending_grams=300)

    assert await fishing.resume_after_restart() == 1
    assert 18 < sched.jobs[11] <= 20


async def test_bite_lost_to_restart_comes_again_with_full_window(factory, monkeypatch) -> None:
    from models import Character

    sched = FakeScheduler()
    monkeypatch.setattr(fishing, "_bite_scheduler", sched)
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    cid = await _player(factory, 12, fishing_cast_at=long_ago, fishing_bite_at=long_ago,
                        fishing_pending_fish="perch", fishing_pending_grams=300)

    await fishing.resume_after_restart()
    assert sched.jobs[12] == pytest.approx(fishing.RESUME_BITE_DELAY_SECONDS, abs=1)
    async with factory() as db:
        bite_at = (await db.get(Character, cid)).fishing_bite_at.replace(tzinfo=timezone.utc)
    window_end = bite_at + timedelta(seconds=fc.STRIKE_WINDOW_SECONDS)
    assert window_end > datetime.now(timezone.utc) + timedelta(seconds=fc.STRIKE_WINDOW_SECONDS - 1)


async def test_dig_is_resumed_and_overdue_one_fires_at_once(factory, monkeypatch) -> None:
    sched = FakeScheduler()
    monkeypatch.setattr(mining, "_dig_scheduler", sched)
    now = datetime.now(timezone.utc)
    await _player(factory, 21, mining_ends_at=now + timedelta(seconds=40))
    await _player(factory, 22, mining_ends_at=now - timedelta(minutes=5))

    assert await mining.resume_after_restart() == 2
    assert 38 < sched.jobs[21] <= 40
    assert sched.jobs[22] == 1.0
