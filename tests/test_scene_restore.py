"""Событие исследования переживает перезапуск бота (2026-10-12): сцена лежит
в Redis под токеном кнопки, нажатие после перезапуска её восстанавливает.
Чужой или старый токен - нет: награду нельзя забрать дважды."""

import pytest

from bot import pending_activity
from bot.handlers import scene_events as h
from game.world import scene_events as se


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)


@pytest.fixture
def redis():
    fake = FakeRedis()
    pending_activity.setup(fake)
    h._pending.clear()
    yield fake
    pending_activity.setup(None)
    h._pending.clear()


async def test_scene_is_restored_after_restart_by_its_token(redis) -> None:
    event = se.content().events[0]
    p = h.Pending(event_id=event.id, scene_id=event.start, token=1760000000123)
    await h._remember(42, p)
    h._pending.clear()  # перезапуск: память пуста, Redis на месте

    restored = await h._restore(42, 1760000000123)
    assert restored is not None
    assert (restored.event_id, restored.scene_id) == (event.id, event.start)
    assert h._pending[42] is restored


async def test_wrong_token_or_finished_event_is_not_restored(redis) -> None:
    event = se.content().events[0]
    await h._remember(42, h.Pending(event_id=event.id, scene_id=event.start, token=5))
    h._pending.clear()
    assert await h._restore(42, 6) is None

    await pending_activity.forget_scene(42)  # событие завершено
    assert await h._restore(42, 5) is None


def test_tokens_do_not_restart_from_one() -> None:
    assert next(h._tokens) > 1_000_000_000
