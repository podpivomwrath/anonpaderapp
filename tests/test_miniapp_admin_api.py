"""Патч 27: /api/miniapp/admin/* — каждый эндпоинт независимо проверяет
request[VK_USER_ID_KEY] == settings.admin_vk_id и отдаёт 403 без данных при
несовпадении (даже с валидной подписью launch-параметров — сама подпись
только удостоверяет vk_id, а не право на админку).

reset_activity здесь НЕ тестируется: он трогает bot.handlers.combat._engine,
живой только внутри main.create_bot (см. докстринг tests/test_moderation.py)."""

import base64
import hashlib
import hmac
from collections import OrderedDict
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app_keys import SESSION_FACTORY_KEY
from bot.webhook import create_app
from config import Settings
from models import Base, Character, CharacterStats, User, Wallet
from services import admin_service

MINIAPP_SECRET = "test_miniapp_secret"
ADMIN_VK_ID = 106468413
PLAYER_VK_ID = 555


def _sign(params: dict[str, str], secret: str) -> str:
    sorted_params = OrderedDict(sorted(params.items()))
    query_string = urlencode(sorted_params, doseq=True)
    digest = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _signed_query(vk_user_id: int) -> dict[str, str]:
    params = {"vk_user_id": str(vk_user_id), "vk_app_id": "1"}
    return {**params, "sign": _sign(params, MINIAPP_SECRET)}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None, vk_miniapp_secret=MINIAPP_SECRET, vk_miniapp_origin="*", admin_vk_id=ADMIN_VK_ID
    )


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(settings, session_factory):
    async def fake_route(event: dict) -> None:
        pass

    app = create_app(settings, fake_route)
    app[SESSION_FACTORY_KEY] = session_factory
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    yield test_client
    await test_client.close()


async def _make_player(session_factory, vk_id: int = PLAYER_VK_ID, **overrides) -> int:
    async with session_factory() as session:
        user = User(vk_id=vk_id)
        session.add(user)
        await session.flush()
        character = Character(
            user_id=user.id, name=f"Игрок{vk_id}", base_class="warrior", level=5, region="ridge",
            pos_x=0, pos_y=0,
        )
        for key, value in overrides.items():
            setattr(character, key, value)
        session.add(character)
        await session.flush()
        session.add(CharacterStats(character_id=character.id))
        session.add(Wallet(character_id=character.id, farm_currency=10))
        await session.commit()
        return character.id


# --- Проверка прав ---


async def test_overview_forbidden_for_non_admin(client) -> None:
    resp = await client.get("/api/miniapp/admin/overview", params=_signed_query(PLAYER_VK_ID))
    assert resp.status == 403
    data = await resp.json()
    assert data == {"error": "forbidden"}


async def test_overview_ok_for_admin(client, session_factory) -> None:
    await _make_player(session_factory)
    resp = await client.get("/api/miniapp/admin/overview", params=_signed_query(ADMIN_VK_ID))
    assert resp.status == 200
    data = await resp.json()
    assert data["players"]["total_characters"] == 1
    assert "progression" in data and "retention" in data and "economy" in data and "combat" in data


async def test_search_forbidden_for_non_admin(client) -> None:
    resp = await client.get(
        "/api/miniapp/admin/search", params={**_signed_query(PLAYER_VK_ID), "q": "Игрок"}
    )
    assert resp.status == 403


async def test_search_finds_player_by_name(client, session_factory) -> None:
    await _make_player(session_factory)
    resp = await client.get(
        "/api/miniapp/admin/search", params={**_signed_query(ADMIN_VK_ID), "q": "Игрок"}
    )
    assert resp.status == 200
    data = await resp.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["vk_id"] == PLAYER_VK_ID


async def test_player_card_forbidden_for_non_admin(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.get(f"/api/miniapp/admin/player/{cid}", params=_signed_query(PLAYER_VK_ID))
    assert resp.status == 403


async def test_player_card_not_found(client) -> None:
    resp = await client.get("/api/miniapp/admin/player/999999", params=_signed_query(ADMIN_VK_ID))
    assert resp.status == 404


async def test_player_card_ok(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.get(f"/api/miniapp/admin/player/{cid}", params=_signed_query(ADMIN_VK_ID))
    assert resp.status == 200
    data = await resp.json()
    assert data["vk_id"] == PLAYER_VK_ID
    assert data["gold"] == 10


# --- Действия ---


async def test_action_forbidden_for_non_admin(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(PLAYER_VK_ID),
        json={"action": "grant_currency", "currency": "farm", "amount": 100},
    )
    assert resp.status == 403


async def test_action_grant_currency(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "grant_currency", "currency": "farm", "amount": 90},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["gold"] == 100


async def test_action_ban_requires_confirm(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "ban", "reason": "спам"},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "confirmation_required"


async def test_action_ban_then_unban(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "ban", "reason": "спам", "confirm": True},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["is_banned"] is True
    assert data["ban_reason"] == "спам"

    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "unban"},
    )
    data = await resp.json()
    assert data["is_banned"] is False


async def test_action_teleport_out_of_bounds_returns_400(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "teleport", "x": 999, "y": 0},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "out_of_bounds"


async def test_action_unknown_returns_400(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    resp = await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "nonexistent"},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "unknown_action"


async def test_action_missing_player_returns_404(client) -> None:
    resp = await client.post(
        "/api/miniapp/admin/player/999999/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "grant_xp", "amount": 100},
    )
    assert resp.status == 404


# --- Журнал ---


async def test_journal_forbidden_for_non_admin(client) -> None:
    resp = await client.get("/api/miniapp/admin/journal", params=_signed_query(PLAYER_VK_ID))
    assert resp.status == 403


async def test_journal_lists_logged_actions(client, session_factory) -> None:
    cid = await _make_player(session_factory)
    await client.post(
        f"/api/miniapp/admin/player/{cid}/action",
        params=_signed_query(ADMIN_VK_ID),
        json={"action": "grant_xp", "amount": 50},
    )
    resp = await client.get("/api/miniapp/admin/journal", params=_signed_query(ADMIN_VK_ID))
    assert resp.status == 200
    data = await resp.json()
    assert len(data["actions"]) == 1
    assert data["actions"][0]["action_type"] == "grant_xp"
    assert data["actions"][0]["target_character_id"] == cid


# --- Репорты багов ---


async def test_bug_reports_forbidden_for_non_admin(client) -> None:
    resp = await client.get("/api/miniapp/admin/bug_reports", params=_signed_query(PLAYER_VK_ID))
    assert resp.status == 403


async def test_bug_reports_list_and_close(client, session_factory) -> None:
    async with session_factory() as db:
        report = await admin_service.create_bug_report(db, None, "не работает", {"level": 1})
        await db.commit()
        report_id = report.id

    resp = await client.get("/api/miniapp/admin/bug_reports", params=_signed_query(ADMIN_VK_ID))
    assert resp.status == 200
    data = await resp.json()
    assert len(data["reports"]) == 1
    assert data["reports"][0]["status"] == "new"

    resp = await client.post(
        f"/api/miniapp/admin/bug_reports/{report_id}/status",
        params=_signed_query(ADMIN_VK_ID),
        json={"status": "closed"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "closed"
