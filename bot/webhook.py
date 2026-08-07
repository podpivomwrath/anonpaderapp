"""aiohttp-сервер, принимающий VK Callback API.

Поток: VK шлёт POST на /vk/callback →
  - type == "confirmation" → отвечаем строкой подтверждения;
  - иначе проверяем secret, дедуплицируем по event_id и СРАЗУ отвечаем "ok",
    обработка события уходит в фоновую задачу.
VK ждёт тело "ok" за миллисекунды; если ответ опаздывает (например, из-за
обработки события синхронно ДО ответа — как было раньше), VK считает
доставку неудачной и повторяет событие, которое обрабатывается как новое
(патч 30, баг 1: дублирующиеся ответы бота и баг-репорты). Ошибки обработчиков
логируются в фоне, наружу это никогда не всплывает — VK уже получил "ok".
"""

import asyncio

from aiohttp import web
from loguru import logger

from bot.app_keys import REDIS_KEY, ROUTE_EVENT_KEY, SESSION_FACTORY_KEY, SETTINGS_KEY, RouteEvent
from bot.miniapp_admin_api import register_routes as register_miniapp_admin_routes
from bot.miniapp_api import register_routes as register_miniapp_routes
from bot.miniapp_auth import miniapp_auth_middleware, miniapp_cors_middleware
from bot.miniapp_map_api import register_routes as register_miniapp_map_routes
from config import Settings
from services.db import get_session_factory

WEBHOOK_PATH = "/vk/callback"

# TTL дедупликации event_id в Redis — с большим запасом на самый упорный
# ретрай-шторм VK (документация не гарантирует точный интервал/число попыток).
EVENT_DEDUP_TTL_SECONDS = 3600


async def _is_duplicate_event(request: web.Request, event_id: str | None) -> bool:
    """True — это событие уже обрабатывалось (или обрабатывается прямо сейчас),
    повторно обрабатывать не нужно. Redis опционален (тесты/локальный dev без
    него) — тогда дедупликации просто нет, как и раньше."""
    if not event_id:
        return False
    redis = request.app.get(REDIS_KEY)
    if redis is None:
        return False
    # SET NX EX атомарен — в отличие от отдельных EXISTS+SETEX, не даёт двум
    # почти одновременным ретраям одного event_id проскочить оба разом.
    was_set = await redis.set(f"vk_event:{event_id}", "1", nx=True, ex=EVENT_DEDUP_TTL_SECONDS)
    return not was_set


async def handle_callback(request: web.Request) -> web.Response:
    settings = request.app[SETTINGS_KEY]
    try:
        event: dict = await request.json()
    except Exception:
        return web.Response(status=400, text="bad request")

    if settings.vk_secret and event.get("secret") != settings.vk_secret:
        logger.warning("Callback с неверным secret: type={}", event.get("type"))
        return web.Response(status=403, text="forbidden")

    event_type = event.get("type")

    if event_type == "confirmation":
        logger.info("Подтверждение сервера для группы {}", event.get("group_id"))
        return web.Response(text=settings.vk_confirmation_code)

    event_id = event.get("event_id")
    if await _is_duplicate_event(request, event_id):
        logger.debug("Дубль события VK проигнорирован: event_id={}", event_id)
        return web.Response(text="ok")

    logger.info(
        "Событие VK: type={} group_id={} event_id={}",
        event_type,
        event.get("group_id"),
        event_id,
    )

    route_event = request.app[ROUTE_EVENT_KEY]

    async def _process() -> None:
        try:
            await route_event(event)
        except Exception:
            logger.exception("Ошибка обработки события {}", event_type)

    asyncio.create_task(_process())
    return web.Response(text="ok")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app(settings: Settings, route_event: RouteEvent, redis=None) -> web.Application:
    app = web.Application(middlewares=[miniapp_cors_middleware, miniapp_auth_middleware])
    app[SETTINGS_KEY] = settings
    app[ROUTE_EVENT_KEY] = route_event
    app[SESSION_FACTORY_KEY] = get_session_factory()
    if redis is not None:
        app[REDIS_KEY] = redis
    app.router.add_post(WEBHOOK_PATH, handle_callback)
    app.router.add_get("/health", handle_health)
    register_miniapp_routes(app)
    register_miniapp_admin_routes(app)
    register_miniapp_map_routes(app)
    return app
