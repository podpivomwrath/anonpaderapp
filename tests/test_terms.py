"""Пользовательское соглашение (2026-10-15): мини-апп и чат не пускают без
согласия; в бою окно не появляется."""

from types import SimpleNamespace

import pytest

from bot.handlers import terms as terms_handlers
from services import terms_service

pytestmark = pytest.mark.real_terms


async def test_accept_sets_current_version(db_session):
    assert not terms_service.accepted(await terms_service.user_of(db_session, 4242))
    await terms_service.accept(db_session, 4242)
    assert terms_service.accepted(await terms_service.user_of(db_session, 4242))


async def test_miniapp_requires_terms_then_lets_in(monkeypatch):
    from tests.test_miniapp_api import MINIAPP_SECRET, _make_character, _signed_query  # noqa: F401
    from aiohttp.test_utils import TestClient, TestServer
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bot.app_keys import SESSION_FACTORY_KEY
    from bot.webhook import create_app
    from config import Settings
    from models import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def route(event):
        pass

    app = create_app(Settings(_env_file=None, vk_miniapp_secret=MINIAPP_SECRET, vk_miniapp_origin="*"), route)
    app[SESSION_FACTORY_KEY] = factory
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        await _make_character(factory, vk_id=5151)
        resp = await client.get("/api/miniapp/character", params=_signed_query(5151))
        assert resp.status == 403 and (await resp.json())["error"] == "terms_required"
        ok = await client.post("/api/miniapp/terms", params=_signed_query(5151))
        assert ok.status == 200
        resp = await client.get("/api/miniapp/character", params=_signed_query(5151))
        assert resp.status == 200
    finally:
        await client.close()
        await engine.dispose()


async def test_chat_gate_waits_for_battle(monkeypatch, db_session, make_character):
    """Посреди боя окно не показываем - только после."""
    c = await make_character()
    sent = []

    class Ctx:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *a): pass

    async def fake_gate(peer_id):
        sent.append(peer_id)

    busy = {"v": True}

    async def fake_busy(db, peer_id):
        return busy["v"]

    monkeypatch.setattr(terms_handlers, "get_session_factory", lambda: Ctx)
    monkeypatch.setattr(terms_handlers, "send_gate", fake_gate)
    monkeypatch.setattr(terms_handlers, "_busy", fake_busy)
    from models import User

    user = await db_session.get(User, c.user_id)
    vk = user.vk_id
    event = SimpleNamespace(from_id=vk, peer_id=vk, get_payload_json=lambda: None)
    mw = terms_handlers.TermsGateMiddleware.__new__(terms_handlers.TermsGateMiddleware)
    stopped = []
    mw.event = event
    mw.stop = lambda reason=None: stopped.append(reason)

    await mw.pre()
    assert sent == [] and stopped == []
    busy["v"] = False
    await mw.pre()
    assert sent == [vk] and stopped == ["terms"]
    await terms_service.accept(db_session, vk)
    sent.clear()
    stopped.clear()
    await mw.pre()
    assert sent == [] and stopped == []
