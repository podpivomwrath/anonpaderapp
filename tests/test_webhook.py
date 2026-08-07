"""Критерий 1: сервер отвечает на confirmation, проверяет secret, роутит события.

Патч 30: обработка события уходит в фоновую задачу (asyncio.create_task) —
ответ "ok" уходит СРАЗУ, не дожидаясь route_event. Тесты, проверяющие, что
событие реально дошло до route_event, ждут его короткий период после ответа."""

import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.webhook import WEBHOOK_PATH, create_app
from config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        vk_confirmation_code="test_code_123",
        vk_secret="s3cret",
    )


@pytest.fixture
async def client_and_events(settings):
    routed: list[dict] = []

    async def fake_route(event: dict) -> None:
        routed.append(event)

    client = TestClient(TestServer(create_app(settings, fake_route)))
    await client.start_server()
    yield client, routed
    await client.close()


async def test_confirmation(client_and_events) -> None:
    client, _ = client_and_events
    resp = await client.post(
        WEBHOOK_PATH,
        json={"type": "confirmation", "group_id": 1, "secret": "s3cret"},
    )
    assert resp.status == 200
    assert await resp.text() == "test_code_123"


async def test_wrong_secret_rejected(client_and_events) -> None:
    client, routed = client_and_events
    resp = await client.post(
        WEBHOOK_PATH,
        json={"type": "message_new", "secret": "wrong", "object": {}},
    )
    assert resp.status == 403
    assert routed == []


async def test_event_routed_and_ok(client_and_events) -> None:
    client, routed = client_and_events
    event = {
        "type": "message_new",
        "group_id": 1,
        "event_id": "abc",
        "secret": "s3cret",
        "object": {"message": {"text": "/start", "from_id": 42}},
    }
    resp = await client.post(WEBHOOK_PATH, json=event)
    assert resp.status == 200
    assert await resp.text() == "ok"
    for _ in range(50):
        if routed:
            break
        await asyncio.sleep(0.01)
    assert len(routed) == 1
    assert routed[0]["type"] == "message_new"


async def test_handler_error_still_ok(settings) -> None:
    async def broken_route(event: dict) -> None:
        raise RuntimeError("boom")

    client = TestClient(TestServer(create_app(settings, broken_route)))
    await client.start_server()
    try:
        resp = await client.post(
            WEBHOOK_PATH,
            json={"type": "message_new", "secret": "s3cret", "object": {}},
        )
        assert resp.status == 200
        assert await resp.text() == "ok"
    finally:
        await client.close()


class _FakeRedis:
    """Минимальная имитация redis.asyncio для SET NX EX — только то, что
    нужно _is_duplicate_event (патч 30, баг 1)."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._keys:
            return False
        self._keys.add(key)
        return True


async def test_duplicate_event_id_processed_once(settings) -> None:
    routed: list[dict] = []

    async def fake_route(event: dict) -> None:
        routed.append(event)

    client = TestClient(TestServer(create_app(settings, fake_route, redis=_FakeRedis())))
    await client.start_server()
    try:
        event = {
            "type": "message_new", "group_id": 1, "event_id": "dup-1", "secret": "s3cret",
            "object": {"message": {"text": "/баг тест", "from_id": 42}},
        }
        first = await client.post(WEBHOOK_PATH, json=event)
        second = await client.post(WEBHOOK_PATH, json=event)  # тот же event_id — ретрай VK
        assert first.status == 200 and await first.text() == "ok"
        assert second.status == 200 and await second.text() == "ok"

        for _ in range(50):
            if routed:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # дать шанс дублю тоже дойти, если бы дедупликация не сработала
        assert len(routed) == 1
    finally:
        await client.close()


async def test_different_event_ids_both_processed(settings) -> None:
    routed: list[dict] = []

    async def fake_route(event: dict) -> None:
        routed.append(event)

    client = TestClient(TestServer(create_app(settings, fake_route, redis=_FakeRedis())))
    await client.start_server()
    try:
        base = {"type": "message_new", "group_id": 1, "secret": "s3cret", "object": {}}
        await client.post(WEBHOOK_PATH, json={**base, "event_id": "a"})
        await client.post(WEBHOOK_PATH, json={**base, "event_id": "b"})

        for _ in range(50):
            if len(routed) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(routed) == 2
    finally:
        await client.close()
