"""Патч 72: эндпоинты мастерской.

Сервис проверяется в test_craft_service.py. Здесь — контракт с мини-аппом:
что подпись обязательна, что решения принимает сервер (а не клиент), и что
отказ не списывает ресурсы.
"""

import base64
import hashlib
import hmac
import random
import time
from collections import OrderedDict
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.app_keys import SESSION_FACTORY_KEY
from bot.webhook import create_app
from config import Settings
from game.economy import craft_config as cc
from models import Base, Character, CharacterOre, CharacterStats, User
from services import item_service

MINIAPP_SECRET = "craft_secret"


def _sign(params: dict[str, str], secret: str) -> str:
    query = urlencode(OrderedDict(sorted(params.items())), doseq=True)
    digest = hmac.new(secret.encode(), query.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _signed(vk_user_id: int) -> dict[str, str]:
    params = {
        "vk_user_id": str(vk_user_id),
        "vk_app_id": "1",
        "vk_ts": str(int(time.time())),
    }
    return {**params, "sign": _sign(params, MINIAPP_SECRET)}


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


VK_ID = 5150


async def _seed(session_factory, *, ore: int = 40, ore_id: str = "brown_iron") -> int:
    """Персонаж со скальпелем и рудой. Возвращает id предмета."""
    async with session_factory() as session:
        user = User(vk_id=VK_ID)
        session.add(user)
        await session.flush()
        character = Character(
            user_id=user.id, name="Кузнец", base_class="warrior",
            region="ridge", pos_x=0, pos_y=0,
        )
        session.add(character)
        await session.flush()
        session.add(CharacterStats(character_id=character.id))
        session.add(
            CharacterOre(character_id=character.id, ore_id=ore_id, grade="common", count=ore)
        )
        item = await item_service.grant_unique_item(
            session, character, "surgeon_scalpel", random.Random(1)
        )
        await session.commit()
        return item.id


# --- Доступ ---------------------------------------------------------------------


async def test_craft_requires_a_signature(client) -> None:
    resp = await client.get("/api/miniapp/craft", params={"vk_user_id": "1"})
    assert resp.status == 403


async def test_craft_post_requires_a_signature(client) -> None:
    resp = await client.post(
        "/api/miniapp/craft",
        params={"vk_user_id": "1"},
        json={"item_id": 1, "spec": "tank", "ore_id": "brown_iron", "grade": "common"},
    )
    assert resp.status == 403


# --- Витрина --------------------------------------------------------------------


async def test_get_craft_lists_everything_the_workshop_needs(client, session_factory) -> None:
    item_id = await _seed(session_factory)
    resp = await client.get("/api/miniapp/craft", params=_signed(VK_ID))
    assert resp.status == 200
    data = await resp.json()

    assert [i["id"] for i in data["items"]] == [item_id]
    assert {s["id"] for s in data["specs"]} == set(cc.SPECS)
    assert data["ore"][0]["count"] == 40
    assert data["efficiency"]["max"] == cc.EFFICIENCY_MAX


async def test_specs_expose_tendency_without_numbers(client, session_factory) -> None:
    """Игрок должен видеть, КУДА целится специализация, но не что выпадет."""
    await _seed(session_factory)
    data = await (await client.get("/api/miniapp/craft", params=_signed(VK_ID))).json()

    tank = next(s for s in data["specs"] if s["id"] == cc.SPEC_TANK)
    assert tank["name"] == "Костяная пила"
    assert tank["lean"][0]["stat"] == "vit"
    assert tank["lean"][0]["share"] == 1.0            # доли от максимума, не веса
    assert all("value" not in row for row in tank["lean"])


async def test_server_computes_the_price(client, session_factory) -> None:
    """Клиент только показывает цену - считать её своими силами он уже
    однажды пытался и врал (патч 57)."""
    await _seed(session_factory)
    data = await (await client.get("/api/miniapp/craft", params=_signed(VK_ID))).json()
    assert data["items"][0]["next_craft_cost"] == cc.CRAFT_ORE_COST


# --- Ковка ----------------------------------------------------------------------


async def test_craft_returns_the_new_weapon(client, session_factory) -> None:
    item_id = await _seed(session_factory)
    resp = await client.post(
        "/api/miniapp/craft", params=_signed(VK_ID),
        json={"item_id": item_id, "spec": cc.SPEC_DPS,
              "ore_id": "brown_iron", "grade": "common"},
    )
    assert resp.status == 200
    data = await resp.json()
    assert data["item"]["name"] == "Тонкий скальпель"
    assert data["item"]["spec"] == cc.SPEC_DPS
    assert data["item"]["efficiency"] == cc.EFFICIENCY_MIN
    assert data["item"]["bound"] is True
    assert data["ore_spent"] == cc.CRAFT_ORE_COST
    assert data["was_recraft"] is False


async def test_craft_with_a_bad_body_is_rejected(client, session_factory) -> None:
    await _seed(session_factory)
    resp = await client.post(
        "/api/miniapp/craft", params=_signed(VK_ID), json={"item_id": "не число"},
    )
    assert resp.status == 400


async def test_craft_without_ore_leaves_everything_alone(client, session_factory) -> None:
    item_id = await _seed(session_factory, ore=1)
    resp = await client.post(
        "/api/miniapp/craft", params=_signed(VK_ID),
        json={"item_id": item_id, "spec": cc.SPEC_TANK,
              "ore_id": "brown_iron", "grade": "common"},
    )
    assert resp.status == 409

    data = await (await client.get("/api/miniapp/craft", params=_signed(VK_ID))).json()
    assert data["ore"][0]["count"] == 1, "отказ не должен списывать руду"
    assert data["items"][0]["spec"] is None


async def test_craft_refuses_someone_elses_item(client, session_factory) -> None:
    item_id = await _seed(session_factory)
    async with session_factory() as session:
        other = User(vk_id=9999)
        session.add(other)
        await session.flush()
        character = Character(
            user_id=other.id, name="Чужак", base_class="mage",
            region="ridge", pos_x=0, pos_y=0,
        )
        session.add(character)
        await session.flush()
        session.add(CharacterStats(character_id=character.id))
        session.add(
            CharacterOre(character_id=character.id, ore_id="brown_iron", grade="common", count=50)
        )
        await session.commit()

    resp = await client.post(
        "/api/miniapp/craft", params=_signed(9999),
        json={"item_id": item_id, "spec": cc.SPEC_TANK,
              "ore_id": "brown_iron", "grade": "common"},
    )
    assert resp.status == 409


# --- Инструменты и ступени -------------------------------------------------------


async def test_tool_then_upgrade_raises_one_step(client, session_factory) -> None:
    item_id = await _seed(session_factory)
    await client.post(
        "/api/miniapp/craft", params=_signed(VK_ID),
        json={"item_id": item_id, "spec": cc.SPEC_TANK,
              "ore_id": "brown_iron", "grade": "common"},
    )
    tool = await client.post(
        "/api/miniapp/craft/tool", params=_signed(VK_ID),
        json={"ore_id": "brown_iron", "grade": "common"},
    )
    assert tool.status == 200
    assert (await tool.json())["ceiling"] == 90

    up = await client.post(
        "/api/miniapp/craft/upgrade", params=_signed(VK_ID),
        json={"item_id": item_id, "ceiling": 90},
    )
    assert up.status == 200
    data = await up.json()
    assert data["efficiency_before"] == 80
    assert data["efficiency_after"] == 90
    assert data["item"]["efficiency"] == 90


async def test_upgrade_with_a_tool_you_do_not_have_is_refused(client, session_factory) -> None:
    item_id = await _seed(session_factory)
    await client.post(
        "/api/miniapp/craft", params=_signed(VK_ID),
        json={"item_id": item_id, "spec": cc.SPEC_TANK,
              "ore_id": "brown_iron", "grade": "common"},
    )
    resp = await client.post(
        "/api/miniapp/craft/upgrade", params=_signed(VK_ID),
        json={"item_id": item_id, "ceiling": 120},
    )
    assert resp.status == 409


async def test_inventory_marks_what_can_go_to_the_workshop(client, session_factory) -> None:
    """Без этой метки игрок с боссовой вещью не узнает, что с ней делать."""
    await _seed(session_factory)
    data = await (await client.get("/api/miniapp/inventory", params=_signed(VK_ID))).json()
    assert data["items"][0]["craftable"] is True
