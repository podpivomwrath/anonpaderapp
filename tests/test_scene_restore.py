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


async def test_choice_event_survives_restart(redis) -> None:
    """2026-10-13: событие с выбором (осколок, шкатулка...) тоже переживает
    рестарт: раньше висело только в памяти, и кнопки молча не работали.
    Цена «Рыбака у воды» возвращается вместе с ним; забрать можно один раз."""
    from bot.handlers import world

    async def getdel(key):
        return redis.data.pop(key, None)

    redis.getdel = getdel
    world._pending_events.pop(555, None)
    world._pending_fish_offers.pop(555, None)
    await pending_activity.remember_event(555, "fish_buyer", 2.5)

    # рестарт: память пуста
    assert await world._pending_event_id(555) == "fish_buyer"
    assert world._pending_fish_offers[555] == 2.5
    assert await pending_activity.recall_event(555) is None  # из Redis забрано разом

    await world._drop_pending_event(555)
    assert await world._pending_event_id(555) is None


def test_mount_coords_accept_natural_formats_and_ignore_words() -> None:
    """2026-10-13: «0 0», «0, 0», «0-0» - тоже координаты; слова (кнопки,
    промокоды) ожидание координат больше не перехватывает."""
    from bot.handlers import mounts

    assert mounts.parse_coords("0 0") == (0, 0)
    assert mounts.parse_coords("0, 0") == (0, 0)
    assert mounts.parse_coords("12-20") == (12, 20)
    assert mounts.parse_coords("-27 -14") == (-27, -14)
    assert mounts.parse_coords("12:-20") == (12, -20)
    for word in ("preal", "📊 Статы", "Босс", "🪨 Руда"):
        assert not mounts._COORD_LIKE_RE.match(word)
