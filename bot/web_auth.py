"""Веб-версия мини-аппа на своём домене (2026-10-15): вход через VK ID.

Внутри VK игрок приходит с подписанными launch-параметрами (bot/miniapp_auth.py).
На сайте их нет, поэтому:

1. Фронт ведёт игрока на id.vk.com/authorize (OAuth 2.1 + PKCE) и получает
   обратно code и device_id.
2. POST /api/web/login обменивает code на сервере (id.vk.com/oauth2/auth) -
   VK сам отвечает, чей это аккаунт; подделать user_id клиент не может.
3. Сервер выдаёт свой ключ сессии «vk_id.срок.подпись» (HMAC), фронт шлёт
   его в Authorization: Bearer. Middleware принимает его наравне с
   launch-параметрами - все /api/miniapp/* работают как в мини-аппе.

Секрет подписи выводится из секрета мини-аппа: отдельной переменной не нужно,
а смена секрета мини-аппа гасит и все веб-сессии.
"""

import base64
import hashlib
import hmac
import time

import aiohttp
from aiohttp import web
from loguru import logger

from bot.app_keys import SETTINGS_KEY
from config import Settings

WEB_PREFIX = "/api/web/"
#: Сколько живёт вход на сайте.
SESSION_TTL_SECONDS = 30 * 24 * 3600
VK_ID_TOKEN_URL = "https://id.vk.com/oauth2/auth"


def _session_secret(settings: Settings) -> bytes:
    return hmac.new(settings.vk_miniapp_secret.encode(), b"web-session-v1", hashlib.sha256).digest()


def _sign(secret: bytes, payload: str) -> str:
    digest = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def make_token(settings: Settings, vk_user_id: int, now: float | None = None) -> str:
    exp = int((now or time.time()) + SESSION_TTL_SECONDS)
    payload = f"{vk_user_id}.{exp}"
    return f"{payload}.{_sign(_session_secret(settings), payload)}"


def verify_token(settings: Settings, token: str, now: float | None = None) -> int | None:
    """vk_id из действующего ключа сессии или None."""
    if not settings.vk_miniapp_secret or not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    uid, exp, sig = parts
    if not hmac.compare_digest(_sign(_session_secret(settings), f"{uid}.{exp}"), sig):
        return None
    try:
        if int(exp) < (now or time.time()):
            return None
        return int(uid)
    except ValueError:
        return None


def bearer_user(request: web.Request) -> int | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return verify_token(request.app[SETTINGS_KEY], header[len("Bearer "):].strip())


async def _exchange_code(settings: Settings, body: dict) -> int | None:
    form = {
        "grant_type": "authorization_code",
        "code": str(body.get("code", "")),
        "code_verifier": str(body.get("code_verifier", "")),
        "device_id": str(body.get("device_id", "")),
        "state": str(body.get("state", "")),
        "redirect_uri": str(body.get("redirect_uri", "")),
        "client_id": settings.vk_id_client_id,
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        async with http.post(VK_ID_TOKEN_URL, data=form) as resp:
            data = await resp.json(content_type=None)
    user_id = data.get("user_id") if isinstance(data, dict) else None
    if not user_id:
        logger.warning("VK ID: обмен кода не удался: {}", data.get("error") if isinstance(data, dict) else data)
        return None
    return int(user_id)


async def handle_config(request: web.Request) -> web.Response:
    settings: Settings = request.app[SETTINGS_KEY]
    return web.json_response({
        "vk_id_client_id": settings.vk_id_client_id or None,
        "demo_login": bool(settings.demo_login and settings.demo_password),
    })


async def handle_login(request: web.Request) -> web.Response:
    settings: Settings = request.app[SETTINGS_KEY]
    if not settings.vk_id_client_id:
        return web.json_response({"error": "web_login_disabled"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict) or not body.get("code") or not body.get("code_verifier"):
        return web.json_response({"error": "bad_request"}, status=400)
    try:
        vk_user_id = await _exchange_code(settings, body)
    except Exception:
        logger.exception("VK ID: ошибка обмена кода")
        vk_user_id = None
    if vk_user_id is None:
        return web.json_response({"error": "login_failed"}, status=401)
    return web.json_response({"token": make_token(settings, vk_user_id), "vk_user_id": vk_user_id})


async def handle_demo_login(request: web.Request) -> web.Response:
    """Вход по логину и паролю в демо-персонажа (проверка ЮKassa). Пускает
    только в settings.demo_vk_id - к настоящим игрокам этот вход не ведёт."""
    import asyncio

    settings: Settings = request.app[SETTINGS_KEY]
    if not settings.demo_login or not settings.demo_password:
        return web.json_response({"error": "demo_disabled"}, status=503)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    login = str((body or {}).get("login", "")).strip()
    password = str((body or {}).get("password", ""))
    ok = hmac.compare_digest(login.encode(), settings.demo_login.encode()) & hmac.compare_digest(
        password.encode(), settings.demo_password.encode(),
    )
    if not ok:
        await asyncio.sleep(1.0)  # перебор паролей - медленно
        return web.json_response({"error": "bad_credentials"}, status=401)
    return web.json_response({"token": make_token(settings, settings.demo_vk_id)})


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/web/config", handle_config)
    app.router.add_post("/api/web/login", handle_login)
    app.router.add_post("/api/web/demo_login", handle_demo_login)
