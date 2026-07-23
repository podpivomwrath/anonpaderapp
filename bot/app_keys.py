"""Общие aiohttp AppKey — вынесены отдельно, чтобы webhook.py и miniapp-модули
могли ссылаться на них без цикличных импортов друг друга."""

from typing import Awaitable, Callable

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings

RouteEvent = Callable[[dict], Awaitable[None]]

SETTINGS_KEY = web.AppKey("settings", Settings)
ROUTE_EVENT_KEY: web.AppKey[RouteEvent] = web.AppKey("route_event")
# Хранится сам sessionmaker (не функция-геттер) — тесты могут подменить его
# на sqlite-фабрику до старта TestServer.
SESSION_FACTORY_KEY: web.AppKey[async_sessionmaker[AsyncSession]] = web.AppKey(
    "miniapp_session_factory"
)
