"""Приложение «Монолит» (2026-11-15, владелец): привязка по коду из мини-аппа.

Логика - services/app_link_service.py. Здесь:
- POST /api/app/pair {code, name, platform} - без входа: код и есть вход.
  Ответ - ключ устройства; дальше приложение ходит во все /api/miniapp/* с
  Authorization: Bearer <ключ> (bot/miniapp_auth.py).
- /api/miniapp/app/* - мини-апп: выдать код, список устройств, отключить.
  Код выдаёт только мини-апп или сайт: из самого приложения нельзя, иначе
  украденный ключ размножал бы себя на новые устройства.
"""

import asyncio

from aiohttp import web
from loguru import logger
from sqlalchemy import select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import APP_DEVICE_KEY, VK_USER_ID_KEY
from models import User
from services import app_link_service as svc

#: Неверный код отвечает не сразу: перебор кода становится ещё дольше.
BAD_CODE_DELAY = 0.7


async def _user(db, request: web.Request) -> User | None:
    return await db.scalar(select(User).where(User.vk_id == request[VK_USER_ID_KEY]))


async def handle_pair(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except ValueError:  # не JSON
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict) or not isinstance(body.get("code"), str):
        return web.json_response({"error": "bad_request"}, status=400)
    async with request.app[SESSION_FACTORY_KEY]() as db:
        try:
            paired = await svc.pair(db, body["code"], str(body.get("name") or ""), str(body.get("platform") or ""))
        except svc.AppLinkError as error:
            await db.commit()  # просроченный код удалён
            if error.code == "bad_code":
                await asyncio.sleep(BAD_CODE_DELAY)
            return web.json_response({"error": error.code}, status=400 if error.code != "too_many_devices" else 409)
        await db.commit()
        logger.info("Приложение: подключено устройство {} ({}) у user {}", paired.device.id,
                    paired.device.platform, paired.device.user_id)
        return web.json_response({
            "token": paired.token, "device_id": paired.device.id, "character": paired.character_name,
        })


async def handle_code(request: web.Request) -> web.Response:
    if APP_DEVICE_KEY in request:
        return web.json_response({"error": "from_app"}, status=403)
    async with request.app[SESSION_FACTORY_KEY]() as db:
        user = await _user(db, request)
        if user is None:
            return web.json_response({"error": "no_character"}, status=404)
        try:
            code, expires = await svc.create_code(db, user)
        except svc.AppLinkError as error:
            return web.json_response({"error": error.code}, status=404)
        await db.commit()
    return web.json_response({"code": code, "expires_at": expires.timestamp(), "seconds": svc.PAIR_CODE_SECONDS})


async def handle_devices(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        user = await _user(db, request)
        devices = await svc.active_devices(db, user.id) if user else []
    current = request.get(APP_DEVICE_KEY)
    return web.json_response({
        "devices": [svc.device_view(d, current) for d in devices], "max": svc.MAX_DEVICES,
    })


async def handle_revoke(request: web.Request) -> web.Response:
    """{"id": N} - отключить устройство; без id из приложения - выйти на нём."""
    try:
        body = await request.json()
    except ValueError:  # не JSON
        body = {}
    device_id = body.get("id") if isinstance(body, dict) else None
    if device_id is None:
        device_id = request.get(APP_DEVICE_KEY)
    if not isinstance(device_id, int) or isinstance(device_id, bool):
        return web.json_response({"error": "bad_request"}, status=400)
    async with request.app[SESSION_FACTORY_KEY]() as db:
        user = await _user(db, request)
        if user is None or not await svc.revoke(db, user.id, device_id):
            return web.json_response({"error": "not_found"}, status=404)
        await db.commit()
    logger.info("Приложение: устройство {} отключено", device_id)
    return web.json_response({"ok": True})


@web.middleware
async def app_admin_guard(request: web.Request, handler):
    """Админка - только из мини-аппа: ключ устройства, даже владельца, туда не
    пускает (утёк ключ с телефона - админ-доступа он не даёт)."""
    if request.path.startswith("/api/miniapp/admin") and APP_DEVICE_KEY in request:
        return web.json_response({"error": "forbidden"}, status=403)
    return await handler(request)


# --- Канал игры: WebSocket /api/app/ws (2026-11-15) --------------------------------
#
# Пока сокет открыт, бот пишет игроку только сюда (bot/app_channel.py). От
# приложения по сокету: {"type": "act", "payload": {...}} - нажатие кнопки,
# {"type": "act", "text": "..."} - ввод словами, {"type": "ping"}.

#: Сколько символов принимаем в «вводе словами» (ник, сумма, код руны).
ACT_TEXT_MAX = 300


def synthetic_message(vk_id: int, group_id: int, text: str = "", payload: dict | None = None) -> dict:
    """Нажатие из приложения в виде события message_new ВК. Номер сообщения 0 -
    так прослойка отличает его от настоящего сообщения из ВК (app_channel)."""
    import json
    import time
    import uuid

    message = {
        "date": int(time.time()), "from_id": vk_id, "peer_id": vk_id, "id": 0, "out": 0, "version": 0,
        "conversation_message_id": 0, "random_id": 0, "text": text, "attachments": [], "fwd_messages": [],
        "important": False, "is_hidden": False,
    }
    if payload is not None:
        message["payload"] = json.dumps(payload, ensure_ascii=False)
    return {
        "type": "message_new", "event_id": f"app-{uuid.uuid4().hex}", "v": "5.199", "group_id": group_id,
        "object": {"message": message, "client_info": {
            "button_actions": ["text", "open_link", "open_app", "location", "vkpay", "callback"],
            "keyboard": True, "inline_keyboard": True, "carousel": False, "lang_id": 0,
        }},
    }


async def resync(vk_id: int) -> None:
    """Приложение подключилось - текущий экран: бой с табло или кнопки клетки."""
    from datetime import datetime, timezone

    from bot import silent_guard
    from bot.battle_keyboard import active_battle_keyboard
    from bot.handlers import combat as combat_handlers
    from bot.handlers import world as world_handlers
    from services.db import get_session_factory
    from services.onboarding_service import get_character

    api = silent_guard._api
    if api is None:
        return
    try:
        keyboard = active_battle_keyboard(vk_id)
        if keyboard is not None:
            text = combat_handlers.board_text(vk_id) or "Идёт бой."
        else:
            async with get_session_factory()() as db:
                character = await get_character(db, vk_id)
                if character is None or character.creation_state is not None:
                    return
                keyboard = await world_handlers._current_keyboard(db, character, vk_id, datetime.now(timezone.utc))
            text = "Вы в игре."
        await api.messages.send(peer_id=vk_id, random_id=0, message=text, keyboard=keyboard)
    except Exception:  # noqa: BLE001 - фоновая задача: что угодно в журнал, канал не роняем
        logger.exception("Приложение: не удалось прислать экран {}", vk_id)


async def handle_ws(request: web.Request) -> web.StreamResponse:
    import json

    from bot import app_channel, background
    from bot.app_keys import ROUTE_EVENT_KEY, SETTINGS_KEY
    from models import Character
    from services.admin_service import is_ban_active

    header = request.headers.get("Authorization", "")
    token = header[len("Bearer "):].strip() if header.startswith("Bearer ") else ""
    async with request.app[SESSION_FACTORY_KEY]() as db:
        found = await svc.device_for_token(db, token)
        if found is None:
            return web.json_response({"error": "app_device_revoked"}, status=403)
        _device, vk_id = found
        character = await db.scalar(select(Character).join(User).where(User.vk_id == vk_id))
        if character is None:
            return web.json_response({"error": "no_character"}, status=404)
        if is_ban_active(character):
            return web.json_response({"error": "account_banned"}, status=403)
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    app_channel.attach(vk_id, ws, character.id)
    route = request.app[ROUTE_EVENT_KEY]
    group_id = request.app[SETTINGS_KEY].vk_group_id
    try:
        await ws.send_json({"type": "hello", "character": character.name})
        background.spawn(resync(vk_id), name="app-resync")
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif data.get("type") == "act":
                payload = data.get("payload")
                text = data.get("text")
                if payload is not None and not isinstance(payload, dict):
                    continue
                text = str(text)[:ACT_TEXT_MAX] if isinstance(text, str) else ""
                if payload is None and not text:
                    continue
                # Подпись кнопки - как текст сообщения: так её видят обработчики и в ВК.
                label = str(data.get("label") or "")[:ACT_TEXT_MAX] if payload is not None else text
                event = synthetic_message(vk_id, group_id, label, payload)
                background.spawn(route(event), name="app-act")
    finally:
        app_channel.detach(vk_id, ws)
    return ws


def register_routes(app: web.Application) -> None:
    app.router.add_post("/api/app/pair", handle_pair)
    app.router.add_get("/api/app/ws", handle_ws)
    app.router.add_post("/api/miniapp/app/code", handle_code)
    app.router.add_get("/api/miniapp/app/devices", handle_devices)
    app.router.add_post("/api/miniapp/app/revoke", handle_revoke)
