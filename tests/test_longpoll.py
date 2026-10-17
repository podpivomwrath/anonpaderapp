"""LongPoll (2026-10-17): события параллельно, повторы с Callback отсекаются
общим ключом в Redis, остановка по сигналу."""

import asyncio
from types import SimpleNamespace

import main


class FakeRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


class FakePolling:
    def __init__(self, batches) -> None:
        self.batches = batches
        self.api = None

    async def listen(self):
        for batch in self.batches:
            yield {"updates": batch}
        await asyncio.sleep(3600)


def _bot(batches, routed: list, slow_first: bool = False):
    async def route(update, api):
        if slow_first and update["event_id"] == "a":
            await asyncio.sleep(0.2)
        routed.append(update["event_id"])

    return SimpleNamespace(polling=FakePolling(batches), api=object(), router=SimpleNamespace(route=route))


def test_longpoll_dedups_and_runs_in_parallel():
    async def scenario():
        routed: list[str] = []
        redis = FakeRedis()
        redis.keys.add("vk_event:c")  # уже пришло через Callback
        bot = _bot([[{"event_id": "a"}, {"event_id": "b"}, {"event_id": "a"}, {"event_id": "c"}]], routed,
                   slow_first=True)
        stop = asyncio.Event()
        runner = asyncio.create_task(main.run_polling(bot, redis, stop))
        await asyncio.sleep(0.05)
        assert routed == ["b"]  # медленное «a» не держит «b»
        await asyncio.sleep(0.3)
        stop.set()
        await asyncio.wait_for(runner, 1)
        return routed

    assert asyncio.run(scenario()) == ["b", "a"]
