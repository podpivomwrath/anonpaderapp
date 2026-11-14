"""Приложение «Монолит» (2026-11-15, владелец): привязка по коду из мини-аппа,
ключ устройства в API мини-аппа, отключение устройства."""

import base64
import hashlib
import hmac
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot import app_api
from bot.app_keys import SESSION_FACTORY_KEY
from bot.webhook import create_app
from config import Settings
from models import AppDevice, AppPairCode, Base, Character, CharacterStats, User, Wallet
from services import app_link_service as svc

SECRET = "test_miniapp_secret"
VK_ID = 777001


def _signed(vk_user_id: int) -> dict[str, str]:
    params = {"vk_user_id": str(vk_user_id), "vk_app_id": "1", "vk_ts": str(int(time.time()))}
    query = urlencode(OrderedDict(sorted(params.items())), doseq=True)
    sign = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).digest())
    return {**params, "sign": sign.decode().rstrip("=")}


@pytest.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(factory, monkeypatch):
    monkeypatch.setattr(app_api, "BAD_CODE_DELAY", 0)
    settings = Settings(_env_file=None, vk_miniapp_secret=SECRET, vk_miniapp_origin="*", admin_vk_id=VK_ID)

    async def route(event: dict) -> None:
        pass

    app = create_app(settings, route)
    app[SESSION_FACTORY_KEY] = factory
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    yield test_client
    await test_client.close()


async def _player(factory, vk_id: int = VK_ID) -> None:
    async with factory() as db:
        user = User(vk_id=vk_id)
        db.add(user)
        await db.flush()
        character = Character(user_id=user.id, name="Пупсик", base_class="warrior", level=5, region="ridge",
                              pos_x=0, pos_y=0)
        db.add(character)
        await db.flush()
        db.add(CharacterStats(character_id=character.id))
        db.add(Wallet(character_id=character.id, farm_currency=10))
        await db.commit()


async def test_code_pair_and_app_uses_miniapp_api(client, factory) -> None:
    await _player(factory)
    resp = await client.post("/api/miniapp/app/code", params=_signed(VK_ID))
    assert resp.status == 200
    code = (await resp.json())["code"]
    assert len(code) == 9 and code[4] == "-"

    # ввёл как попало: строчными и без дефиса
    resp = await client.post("/api/app/pair", json={"code": code.replace("-", " ").lower(),
                                                    "name": "Мой ПК", "platform": "windows"})
    assert resp.status == 200
    paired = await resp.json()
    assert paired["character"] == "Пупсик" and paired["token"].startswith("app1.")
    headers = {"Authorization": f"Bearer {paired['token']}"}

    # тот же API, что у мини-аппа
    resp = await client.get("/api/miniapp/character", headers=headers)
    assert resp.status == 200 and (await resp.json())["name"] == "Пупсик"

    # код одноразовый
    resp = await client.post("/api/app/pair", json={"code": code, "name": "x", "platform": "android"})
    assert resp.status == 400 and (await resp.json())["error"] == "bad_code"

    # из приложения новый код не выдать, админку не открыть
    assert (await client.post("/api/miniapp/app/code", headers=headers)).status == 403
    assert (await client.get("/api/miniapp/admin/overview", headers=headers)).status == 403

    # мини-апп видит устройство и отключает его - ключ перестаёт работать
    devices = (await (await client.get("/api/miniapp/app/devices", params=_signed(VK_ID))).json())["devices"]
    assert [d["name"] for d in devices] == ["Мой ПК"] and devices[0]["platform"] == "windows"
    resp = await client.post("/api/miniapp/app/revoke", params=_signed(VK_ID), json={"id": devices[0]["id"]})
    assert resp.status == 200
    resp = await client.get("/api/miniapp/character", headers=headers)
    assert resp.status == 403 and (await resp.json())["error"] == "app_device_revoked"


async def test_app_can_log_itself_out(client, factory) -> None:
    await _player(factory)
    code = (await (await client.post("/api/miniapp/app/code", params=_signed(VK_ID))).json())["code"]
    token = (await (await client.post("/api/app/pair", json={"code": code, "platform": "android"})).json())["token"]
    headers = {"Authorization": f"Bearer {token}"}
    devices = (await (await client.get("/api/miniapp/app/devices", headers=headers)).json())["devices"]
    assert devices[0]["current"] is True and devices[0]["name"] == "Телефон"
    assert (await client.post("/api/miniapp/app/revoke", headers=headers, json={})).status == 200
    assert (await client.get("/api/miniapp/character", headers=headers)).status == 403


async def test_wrong_and_expired_codes(client, factory) -> None:
    await _player(factory)
    resp = await client.post("/api/app/pair", json={"code": "ABCD-EFGH", "platform": "windows"})
    assert resp.status == 400
    assert (await client.post("/api/app/pair", json={"code": "x", "platform": "ios"})).status == 400
    code = (await (await client.post("/api/miniapp/app/code", params=_signed(VK_ID))).json())["code"]
    async with factory() as db:
        row = (await db.execute(AppPairCode.__table__.select())).first()
        await db.execute(AppPairCode.__table__.update().values(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    assert row is not None
    resp = await client.post("/api/app/pair", json={"code": code, "platform": "windows"})
    assert resp.status == 400 and (await resp.json())["error"] == "bad_code"


async def test_new_code_replaces_old_and_device_limit(factory) -> None:
    await _player(factory)
    async with factory() as db:
        user = (await db.execute(User.__table__.select())).first()
        user = await db.get(User, user.id)
        first, _ = await svc.create_code(db, user)
        second, _ = await svc.create_code(db, user)
        with pytest.raises(svc.AppLinkError):
            await svc.pair(db, first, "a", "windows")
        for i in range(svc.MAX_DEVICES):
            code, _ = await svc.create_code(db, user)
            await svc.pair(db, code, f"d{i}", "android")
        code, _ = await svc.create_code(db, user)
        with pytest.raises(svc.AppLinkError) as err:
            await svc.pair(db, code, "лишний", "android")
        assert err.value.code == "too_many_devices"
        # отключил одно - тот же код подходит
        device = (await svc.active_devices(db, user.id))[0]
        assert await svc.revoke(db, user.id, device.id)
        paired = await svc.pair(db, code, "лишний", "android")
        assert isinstance(paired.device, AppDevice) and second
