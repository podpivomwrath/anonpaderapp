"""Критерий 1: сервер отвечает на confirmation, проверяет secret, роутит события."""

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
