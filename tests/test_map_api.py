"""Патч 29: /api/miniapp/map/state и /api/miniapp/map/send_mount.

combat_handlers.has_active_encounter требует инициализированный _engine
(main.create_bot) — monkeypatch подставляет минимальный фейк с пустым
.sessions, по образцу остальных тестов, трогающих bot/handlers/combat.py."""

import base64
import hashlib
import hmac
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bot.handlers.combat as combat_handlers
import bot.handlers.mounts as mounts_handlers
from bot.app_keys import SESSION_FACTORY_KEY
from bot.webhook import create_app
from config import Settings
from models import Base, Character, CharacterMount, CharacterStats, MountTravel, User

MINIAPP_SECRET = "test_miniapp_secret"
PLAYER_VK_ID = 777


class _FakeMessages:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs) -> int:
        self.sent.append(kwargs)
        return len(self.sent)


class _FakeBotApi:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


@pytest.fixture(autouse=True)
def _fake_mounts_bot_api(monkeypatch):
    """Патч 31, фикс 1: send_mount с карты теперь шлёт то же чат-уведомление,
    что и отправка из чата (bot/handlers/mounts.py::notify_travel_started) —
    без bot_api эта функция раньше была no-op (см. её докстринг)."""
    fake = _FakeBotApi()
    monkeypatch.setattr(mounts_handlers, "_bot_api", fake)
    return fake


def _sign(params: dict[str, str], secret: str) -> str:
    sorted_params = OrderedDict(sorted(params.items()))
    query_string = urlencode(sorted_params, doseq=True)
    digest = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _signed_query(vk_user_id: int) -> dict[str, str]:
    params = {"vk_user_id": str(vk_user_id), "vk_app_id": "1"}
    return {**params, "sign": _sign(params, MINIAPP_SECRET)}


class _FakeEngine:
    sessions: dict = {}


@pytest.fixture(autouse=True)
def _fake_combat_engine(monkeypatch):
    monkeypatch.setattr(combat_handlers, "_engine", _FakeEngine())


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


async def _make_player(session_factory, vk_id: int = PLAYER_VK_ID, **overrides) -> Character:
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
        await session.commit()
        return character


# --- GET /api/miniapp/map/state ---


async def test_state_requires_signature(client) -> None:
    resp = await client.get("/api/miniapp/map/state")
    assert resp.status == 403


async def test_state_character_not_found(client) -> None:
    resp = await client.get("/api/miniapp/map/state", params=_signed_query(999999))
    assert resp.status == 404


async def test_state_returns_position_and_catalog(client, session_factory) -> None:
    await _make_player(session_factory)
    resp = await client.get("/api/miniapp/map/state", params=_signed_query(PLAYER_VK_ID))
    assert resp.status == 200
    data = await resp.json()
    assert data["pos_x"] == 0 and data["pos_y"] == 0
    assert data["foot_travel"] is None
    assert data["mount_travel"] is None
    assert data["mounts"] == []
    catalog = data["catalog"]
    assert catalog["bounds_min"] == -50 and catalog["bounds_max"] == 50
    assert catalog["city_coords"]["ridge"] == [50, 50]
    assert len(catalog["zone_table"]) == 5
    assert set(catalog["location_types"]) == {"ridge", "woods", "docks", "scorched"}
    assert len(catalog["location_types"]["ridge"]) == 4


async def test_state_reports_owned_mounts_without_active_travel(client, session_factory) -> None:
    """Ветки foot_travel/mount_travel с НЕ-null таймстампом (is_traveling/
    remaining_seconds сравнивают его с datetime.now(timezone.utc)) здесь не
    тестируются: SQLite (тестовая БД) не хранит tzinfo — round-trip даёт
    наивный datetime, а aware-vs-naive сравнение падает. Тот же документированный
    компромисс, что и в tests/test_mount_service.py (см. его докстринг); на
    Postgres (прод) tzinfo переживает round-trip как есть — подтверждено вручную
    через живой запрос к dev-БД при разработке патча 29. Здесь проверяем то, что
    воспроизводимо на SQLite: список маунтов при отсутствии активного пути."""
    character = await _make_player(session_factory)
    async with session_factory() as db:
        db.add(CharacterMount(character_id=character.id, mount_id="ashen_steed"))
        await db.commit()

    resp = await client.get("/api/miniapp/map/state", params=_signed_query(PLAYER_VK_ID))
    data = await resp.json()
    assert data["foot_travel"] is None
    assert data["mount_travel"] is None
    assert len(data["mounts"]) == 1
    assert data["mounts"][0]["mount_id"] == "ashen_steed"


# --- POST /api/miniapp/map/send_mount ---


async def test_send_mount_requires_signature(client) -> None:
    resp = await client.post("/api/miniapp/map/send_mount", json={"mount_id": "ashen_steed", "x": 1, "y": 1})
    assert resp.status == 403


async def test_send_mount_bad_request_on_missing_fields(client, session_factory) -> None:
    await _make_player(session_factory)
    resp = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID), json={"mount_id": "ashen_steed"}
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "bad_request"


async def test_send_mount_rejects_unowned_mount(client, session_factory) -> None:
    await _make_player(session_factory)
    resp = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 5, "y": 5},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "mount_not_owned"


async def test_send_mount_rejects_out_of_bounds(client, session_factory) -> None:
    character = await _make_player(session_factory)
    async with session_factory() as db:
        db.add(CharacterMount(character_id=character.id, mount_id="ashen_steed"))
        await db.commit()

    resp = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 999, "y": 0},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "out_of_bounds"


async def test_send_mount_rejects_same_cell(client, session_factory) -> None:
    character = await _make_player(session_factory)
    async with session_factory() as db:
        db.add(CharacterMount(character_id=character.id, mount_id="ashen_steed"))
        await db.commit()

    resp = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 0, "y": 0},
    )
    assert resp.status == 400
    data = await resp.json()
    assert data["error"] == "already_there"


async def test_send_mount_starts_travel(client, session_factory, _fake_mounts_bot_api) -> None:
    character = await _make_player(session_factory)
    async with session_factory() as db:
        db.add(CharacterMount(character_id=character.id, mount_id="ashen_steed"))
        await db.commit()

    resp = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 10, "y": 0},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["to_x"] == 10 and data["to_y"] == 0
    assert data["seconds"] == pytest.approx(10 * 7.0)  # rare: 7 сек/клетка
    assert data["ambush_chance"] == pytest.approx(0.20)

    async with session_factory() as db:
        travel = await db.get(MountTravel, data["travel_id"])
        assert travel.status == "traveling"
        assert (travel.to_x, travel.to_y) == (10, 0)

    # Патч 31, фикс 1: игрок должен получить в чат то же сообщение о начале
    # пути, что и при отправке из чата — раньше send_mount с карты создавал
    # MountTravel полностью молча.
    assert len(_fake_mounts_bot_api.messages.sent) == 1
    sent = _fake_mounts_bot_api.messages.sent[0]
    assert sent["peer_id"] == PLAYER_VK_ID
    assert "Путь начат" in sent["message"]
    assert sent["keyboard"] is not None


async def test_send_mount_rejects_second_travel(client, session_factory) -> None:
    character = await _make_player(session_factory)
    async with session_factory() as db:
        db.add(CharacterMount(character_id=character.id, mount_id="ashen_steed"))
        await db.commit()

    first = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 10, "y": 0},
    )
    assert first.status == 200

    second = await client.post(
        "/api/miniapp/map/send_mount", params=_signed_query(PLAYER_VK_ID),
        json={"mount_id": "ashen_steed", "x": 20, "y": 0},
    )
    assert second.status == 400
    data = await second.json()
    assert data["error"] == "already_on_mount"


def test_blocked_reason_dead_character_in_memory() -> None:
    """_blocked_reason принимает Character напрямую — конструируем его в
    памяти (без записи/чтения из БД), чтобы обойти SQLite tzinfo round-trip
    (см. докстринг выше) и всё же проверить гейт "мёртв" по-настоящему."""
    from bot.miniapp_map_api import _blocked_reason

    character = Character(
        user_id=1, name="x", base_class="warrior",
        respawn_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    assert _blocked_reason(character, peer_id=1) == "dead"


def test_blocked_reason_none_when_free() -> None:
    from bot.miniapp_map_api import _blocked_reason

    character = Character(user_id=1, name="x", base_class="warrior")
    assert _blocked_reason(character, peer_id=1) is None
