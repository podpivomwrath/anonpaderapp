"""Проверка подписи launch-параметров VK Mini App.

VK при открытии мини-аппа добавляет к URL query-параметры vk_user_id, vk_app_id
и т.д. плюс sign — HMAC-SHA256(vk_* параметры, отсортированные и urlencode'нутые)
секретным ключом приложения, base64 url-safe без padding. Алгоритм — из
официальной документации VK Mini Apps.

Middleware проверяет подпись на КАЖДОМ /api/miniapp/* запросе и кладёт
проверенный vk_user_id в request — клиент не может подделать "своего" игрока.
"""

import base64
import hashlib
import hmac
from collections import OrderedDict
from typing import Awaitable, Callable
from urllib.parse import urlencode

from aiohttp import web
from loguru import logger

from bot.app_keys import SETTINGS_KEY
from config import Settings

VK_USER_ID_KEY: web.RequestKey[int] = web.RequestKey("vk_user_id")

MINIAPP_PREFIX = "/api/miniapp/"


def verify_launch_params(params: dict[str, str], secret: str) -> bool:
    """True, если подпись `sign` соответствует остальным vk_-параметрам."""
    if not secret:
        return False
    sign = params.get("sign")
    if not sign:
        return False

    vk_params = {k: v for k, v in params.items() if k.startswith("vk_")}
    if not vk_params:
        return False

    sorted_params = OrderedDict(sorted(vk_params.items()))
    query_string = urlencode(sorted_params, doseq=True)

    digest = hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).digest()
    expected = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    return hmac.compare_digest(expected, sign)


@web.middleware
async def miniapp_auth_middleware(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    if not request.path.startswith(MINIAPP_PREFIX):
        return await handler(request)

    settings: Settings = request.app[SETTINGS_KEY]
    params = dict(request.query)

    if not verify_launch_params(params, settings.vk_miniapp_secret):
        logger.warning("Miniapp: неверная подпись launch-параметров, путь={}", request.path)
        return web.json_response({"error": "invalid_signature"}, status=403)

    try:
        vk_user_id = int(params["vk_user_id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "invalid_signature"}, status=403)

    request[VK_USER_ID_KEY] = vk_user_id
    return await handler(request)


@web.middleware
async def miniapp_cors_middleware(
    request: web.Request, handler: Callable[[web.Request], Awaitable[web.Response]]
) -> web.Response:
    """CORS только для /api/miniapp/*: остальным путям (Callback API, health)
    браузерный CORS не нужен — они не вызываются из фронтенда мини-аппа."""
    if not request.path.startswith(MINIAPP_PREFIX):
        return await handler(request)

    settings: Settings = request.app[SETTINGS_KEY]
    origin = settings.vk_miniapp_origin

    if request.method == "OPTIONS":
        response = web.Response()
    else:
        response = await handler(request)

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response
