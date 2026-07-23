"""aiohttp-сервер, принимающий VK Callback API.

Поток: VK шлёт POST на /vk/callback →
  - type == "confirmation" → отвечаем строкой подтверждения;
  - иначе проверяем secret, логируем и передаём событие в route_event
    (в проде это bot.router.route из vkbottle, в тестах — стаб).
VK ждёт тело "ok"; при любом другом ответе событие будет ретраиться,
поэтому ошибки обработчиков логируются, но наружу отдаётся "ok".
"""

from aiohttp import web
from loguru import logger

from bot.app_keys import ROUTE_EVENT_KEY, SESSION_FACTORY_KEY, SETTINGS_KEY, RouteEvent
from bot.miniapp_api import register_routes as register_miniapp_routes
from bot.miniapp_auth import miniapp_auth_middleware, miniapp_cors_middleware
from config import Settings
from services.db import get_session_factory

WEBHOOK_PATH = "/vk/callback"


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

    logger.info(
        "Событие VK: type={} group_id={} event_id={}",
        event_type,
        event.get("group_id"),
        event.get("event_id"),
    )

    route_event = request.app[ROUTE_EVENT_KEY]
    try:
        await route_event(event)
    except Exception:
        # Отвечаем "ok" в любом случае, иначе VK будет бесконечно ретраить событие
        logger.exception("Ошибка обработки события {}", event_type)
    return web.Response(text="ok")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app(settings: Settings, route_event: RouteEvent) -> web.Application:
    app = web.Application(middlewares=[miniapp_cors_middleware, miniapp_auth_middleware])
    app[SETTINGS_KEY] = settings
    app[ROUTE_EVENT_KEY] = route_event
    app[SESSION_FACTORY_KEY] = get_session_factory()
    app.router.add_post(WEBHOOK_PATH, handle_callback)
    app.router.add_get("/health", handle_health)
    register_miniapp_routes(app)
    return app
