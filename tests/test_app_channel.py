"""Канал приложения (2026-11-15, владелец: «бот должен молчать, работать
только в одном месте»): пока приложение открыто, бот пишет туда, а не в ВК."""

import json
from types import SimpleNamespace

import pytest

from bot import app_channel, silent_guard


class _Ws:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.closed = False

    async def send_json(self, event: dict) -> None:
        self.events.append(event)

    async def close(self) -> None:
        self.closed = True


class _Api:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def request(self, method, data, version=None):
        self.calls.append((method, data))
        return {"response": 42}


@pytest.fixture(autouse=True)
def _no_world_snapshots(monkeypatch):
    """Снимок мира ходит в базу - здесь проверяем только канал."""
    from bot import app_state

    monkeypatch.setattr(app_state, "refresh_soon", lambda vk_id: None)


@pytest.fixture
def api():
    fake = _Api()
    silent_guard.install(fake)
    return fake


@pytest.fixture
def ws():
    socket = _Ws()
    app_channel.attach(5101, socket)
    yield socket
    app_channel.detach(5101, socket)


KEYBOARD = json.dumps({"one_time": False, "buttons": [[
    {"action": {"type": "text", "label": "🔍 Исследовать", "payload": json.dumps({"cmd": "explore", "k": 1})},
     "color": "primary"},
]]})


async def test_send_goes_to_app_not_vk(api, ws) -> None:
    resp = await api.request("messages.send", {"peer_id": 5101, "message": "Клетка (3; 4)", "keyboard": KEYBOARD,
                                               "attachment": "photo-1_2", "random_id": 0})
    assert api.calls == []
    event = ws.events[-1]
    assert event["type"] == "message" and event["text"] == "Клетка (3; 4)"
    assert event["keyboard"]["rows"][0][0] == {
        "label": "🔍 Исследовать", "type": "text", "payload": {"cmd": "explore", "k": 1}, "color": "primary",
        "link": None,
    }
    assert event["attachments"] == ["photo-1_2"]
    assert app_channel.is_fake(resp["response"]) and app_channel.owner_of(resp["response"]) == 5101
    assert event["id"] == str(resp["response"])

    # message.answer шлёт peer_ids списком - ответ списком, как у VK
    resp = await api.request("messages.send", {"peer_ids": [5101], "message": "x", "random_id": 0})
    assert resp["response"][0]["peer_id"] == 5101 and app_channel.is_fake(resp["response"][0]["message_id"])
    assert api.calls == []


async def test_broadcast_splits_app_and_vk(api, ws) -> None:
    await api.request("messages.send", {"peer_ids": "5101,5102,5103", "message": "Мировой босс", "random_id": 0})
    assert ws.events[-1]["text"] == "Мировой босс"
    assert api.calls == [("messages.send", {"message": "Мировой босс", "random_id": 0, "peer_ids": "5102,5103"})]


async def test_edit_and_delete_of_app_windows(api, ws) -> None:
    sent = (await api.request("messages.send", {"peer_id": 5101, "message": "в пути 0:30", "random_id": 0}))["response"]
    await api.request("messages.edit", {"peer_id": 5101, "message_id": sent, "message": "в пути 0:20"})
    assert ws.events[-1] == {**ws.events[-1], "type": "edit", "id": str(sent), "text": "в пути 0:20"}
    # правка старого окна в ВК, пока игрок в приложении - молча
    assert await api.request("messages.edit", {"peer_id": 5101, "message_id": 77, "message": "x"}) == {"response": 1}
    await api.request("messages.delete", {"message_ids": [sent], "delete_for_all": True})
    assert ws.events[-1]["type"] == "delete" and ws.events[-1]["ids"] == [str(sent)]
    assert api.calls == []


async def test_after_app_closed_vk_works_and_app_window_edit_fails(api) -> None:
    socket = _Ws()
    app_channel.attach(5201, socket)
    sent = (await api.request("messages.send", {"peer_id": 5201, "message": "окно", "random_id": 0}))["response"]
    app_channel.detach(5201, socket)
    from vkbottle.exception_factory.base_exceptions import VKAPIError

    with pytest.raises(VKAPIError):
        await api.request("messages.edit", {"peer_id": 5201, "message_id": sent, "message": "x"})
    await api.request("messages.send", {"peer_id": 5201, "message": "снова в ВК", "random_id": 0})
    assert api.calls[-1][1]["message"] == "снова в ВК"


async def test_writing_in_vk_releases_the_app(ws, monkeypatch) -> None:
    import asyncio

    from bot import notices

    monkeypatch.setattr(app_channel, "MOVED_CLOSE_DELAY", 0)

    class _Labeler:
        def __init__(self) -> None:
            self.middlewares = []
            self.message_view = SimpleNamespace(register_middleware=self.middlewares.append)

        def raw_event(self, *args, **kwargs):
            return lambda fn: fn

    labeler = _Labeler()
    notices.register(SimpleNamespace(labeler=labeler, on=labeler))
    middleware = labeler.middlewares[0].__new__(labeler.middlewares[0])

    middleware.event = SimpleNamespace(from_id=5101, peer_id=5101, id=0)  # нажатие из приложения
    await middleware.pre()
    assert app_channel.active(5101)

    middleware.event = SimpleNamespace(from_id=5101, peer_id=5101, id=123456)  # настоящее из ВК
    await middleware.pre()
    assert not app_channel.active(5101)
    assert ws.events[-1]["type"] == "moved" and not ws.closed  # закрытие - чуть позже, чтобы moved дошёл
    await asyncio.sleep(0.05)
    assert ws.closed


async def test_ws_hello_and_act_routes_button_press(monkeypatch) -> None:
    from aiohttp.test_utils import TestClient, TestServer
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bot.app_keys import SESSION_FACTORY_KEY
    from bot.webhook import create_app
    from config import Settings
    from models import Base, Character, CharacterStats, User
    from services import app_link_service as svc

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = User(vk_id=5301)
        db.add(user)
        await db.flush()
        character = Character(user_id=user.id, name="Сокет", base_class="mage", level=3, region="ridge",
                              pos_x=0, pos_y=0)
        db.add(character)
        await db.flush()
        db.add(CharacterStats(character_id=character.id))
        code, _ = await svc.create_code(db, user)
        token = (await svc.pair(db, code, "ПК", "windows")).token
        await db.commit()

    routed: list[dict] = []

    async def route(event: dict) -> None:
        routed.append(event)

    app = create_app(Settings(_env_file=None, vk_miniapp_secret="s", vk_group_id=77), route)
    app[SESSION_FACTORY_KEY] = factory
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        bad = await client.get("/api/app/ws", headers={"Authorization": "Bearer app1.nope"})
        assert bad.status == 403
        socket = await client.ws_connect("/api/app/ws", headers={"Authorization": f"Bearer {token}"})
        hello = await socket.receive_json()
        assert hello == {"type": "hello", "character": "Сокет"}
        assert app_channel.active(5301)
        await socket.send_json({"type": "act", "label": "🔍 Исследовать", "payload": {"cmd": "explore"}})
        await socket.send_json({"type": "ping"})
        assert (await socket.receive_json())["type"] == "pong"
        await socket.close()
    finally:
        await client.close()
        await engine.dispose()
    assert not app_channel.active(5301)
    message = routed[0]["object"]["message"]
    assert routed[0]["type"] == "message_new" and routed[0]["group_id"] == 77
    assert message["from_id"] == message["peer_id"] == 5301 and message["id"] == 0
    assert json.loads(message["payload"]) == {"cmd": "explore"} and message["text"] == "🔍 Исследовать"
