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


def register_routes(app: web.Application) -> None:
    app.router.add_post("/api/app/pair", handle_pair)
    app.router.add_post("/api/miniapp/app/code", handle_code)
    app.router.add_get("/api/miniapp/app/devices", handle_devices)
    app.router.add_post("/api/miniapp/app/revoke", handle_revoke)
