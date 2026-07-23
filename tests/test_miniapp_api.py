"""Мини-апп API: подпись launch-параметров, GET/POST статов.

Использует свой собственный движок+sessionmaker (не фикстуру db_session из
conftest), потому что нужно передать САМ sessionmaker в приложение через
SESSION_FACTORY_KEY — sqlite :memory: держит все сессии на одном соединении
(StaticPool), так что данные видны и из тестовой подготовки, и из хендлеров.
"""

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
from models import Base, Character, CharacterStats, User

MINIAPP_SECRET = "test_miniapp_secret"


def _sign(params: dict[str, str], secret: str) -> str:
    sorted_params = OrderedDict(sorted(params.items()))
    query_string = urlencode(sorted_params, doseq=True)
    digest = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _signed_query(vk_user_id: int, secret: str = MINIAPP_SECRET) -> dict[str, str]:
    params = {"vk_user_id": str(vk_user_id), "vk_app_id": "1"}
    return {**params, "sign": _sign(params, secret)}


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, vk_miniapp_secret=MINIAPP_SECRET, vk_miniapp_origin="*")


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


async def _make_character(
    session_factory, vk_id: int, subclass: str | None = None, **stat_overrides
) -> Character:
    async with session_factory() as session:
        user = User(vk_id=vk_id)
        session.add(user)
        await session.flush()
        character = Character(
            user_id=user.id,
            name=f"Герой{vk_id}",
            base_class="warrior",
            level=5,
            region="ridge",
            subclass=subclass,
        )
        session.add(character)
        await session.flush()
        stats = CharacterStats(character_id=character.id, unspent_points=3, **stat_overrides)
        session.add(stats)
        await session.commit()
        return character


# --- Подпись ---


async def test_valid_signature_returns_character(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=111)
    resp = await client.get("/api/miniapp/character", params=_signed_query(111))
    assert resp.status == 200
    data = await resp.json()
    assert data["name"] == "Герой111"
    assert data["base_class"] == "warrior"
    assert data["unspent_points"] == 3
    assert "derived" in data and "max_hp" in data["derived"]


async def test_tampered_signature_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=112)
    query = _signed_query(112)
    query["vk_user_id"] = "999"  # подменили игрока, sign остался старым
    resp = await client.get("/api/miniapp/character", params=query)
    assert resp.status == 403


async def test_missing_signature_rejected(client) -> None:
    resp = await client.get("/api/miniapp/character", params={"vk_user_id": "111"})
    assert resp.status == 403


async def test_wrong_secret_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=113)
    resp = await client.get(
        "/api/miniapp/character", params=_signed_query(113, secret="wrong_secret")
    )
    assert resp.status == 403


async def test_character_not_found(client) -> None:
    resp = await client.get("/api/miniapp/character", params=_signed_query(999))
    assert resp.status == 404


# --- POST /api/miniapp/stats ---


async def test_apply_valid_increment(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=200)
    resp = await client.post(
        "/api/miniapp/stats", params=_signed_query(200), json={"vit": 2, "str": 1}
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["unspent_points"] == 0
    assert data["stats"]["vit"] == 17
    assert data["stats"]["str"] == 16


async def test_exceeds_unspent_points_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=201)
    resp = await client.post("/api/miniapp/stats", params=_signed_query(201), json={"vit": 4})
    assert resp.status == 400

    # ничего не применилось
    check = await client.get("/api/miniapp/character", params=_signed_query(201))
    data = await check.json()
    assert data["unspent_points"] == 3
    assert data["stats"]["vit"] == 15


async def test_negative_increment_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=202)
    resp = await client.post("/api/miniapp/stats", params=_signed_query(202), json={"vit": -1})
    assert resp.status == 400


async def test_non_integer_increment_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=203)
    resp = await client.post("/api/miniapp/stats", params=_signed_query(203), json={"vit": 1.5})
    assert resp.status == 400


async def test_nothing_to_apply_rejected(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=204)
    resp = await client.post("/api/miniapp/stats", params=_signed_query(204), json={})
    assert resp.status == 400


# --- GET /api/miniapp/trials (патч 12) ---


async def test_trials_empty_without_subclass(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=300)
    resp = await client.get("/api/miniapp/trials", params=_signed_query(300))
    assert resp.status == 200
    data = await resp.json()
    assert data == {"subclass": None, "trials": []}


async def test_trials_lists_full_pool_with_progress(client, session_factory) -> None:
    character = await _make_character(session_factory, vk_id=301, subclass="guardian")
    async with session_factory() as session:
        from game.combat.battle_report import BattleReport
        from services import trial_service

        db_character = await session.get(Character, character.id)
        report = BattleReport(won=True, hp_min_pct=0.05, max_hp=100)  # survive_hp_floor 10%
        await trial_service.record_battle(session, db_character, report)
        await session.commit()

    resp = await client.get("/api/miniapp/trials", params=_signed_query(301))
    assert resp.status == 200
    data = await resp.json()
    assert data["subclass"] == "guardian"
    assert len(data["trials"]) == 14
    bulwark = next(t for t in data["trials"] if t["id"] == "guardian_bulwark")
    assert bulwark["unlocked"] is True
    assert bulwark["buff_name"] == "Несокрушимость"
    other = next(t for t in data["trials"] if t["id"] == "guardian_command")
    assert other["unlocked"] is False
    assert other["progress"] == 0
    assert other["target"] == 25


# --- CORS ---


async def test_cors_preflight_no_signature_needed(client) -> None:
    resp = await client.options(
        "/api/miniapp/character",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status == 200
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


async def test_cors_header_on_real_response(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=205)
    resp = await client.get("/api/miniapp/character", params=_signed_query(205))
    assert resp.headers["Access-Control-Allow-Origin"] == "*"
