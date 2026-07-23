"""Точка входа: aiohttp-сервер (Callback API) + vkbottle + тик-движок."""

import asyncio
import sys

import redis.asyncio as aioredis
from aiohttp import web
from loguru import logger
from vkbottle import Bot

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.handlers import LABELERS, onboarding
from bot.handlers import combat as combat_handlers
from bot.handlers import respawn as respawn_handlers
from bot.handlers import world as world_handlers
from bot.webhook import WEBHOOK_PATH, create_app
from config import Settings, get_settings
from game.combat.duel_engine import DuelEngine
from game.combat.tick_engine import RedisActionStore, TickEngine
from game.world.scheduler import PeerScheduler
from services.db import dispose_engine


def create_bot(settings: Settings) -> Bot:
    bot = Bot(token=settings.vk_token)
    for labeler in LABELERS:
        bot.labeler.load(labeler)
    onboarding.setup(bot)  # диспенсер состояний + восстановление FSM из БД
    return bot


async def run_polling(bot: Bot) -> None:
    """LongPoll-цикл: те же хендлеры и роутер, что и у Callback API."""
    logger.info("Режим LongPoll: опрашиваем VK, публичный URL не нужен")
    bot.polling.api = bot.api
    async for event in bot.polling.listen():
        for update in event.get("updates", []):
            try:
                await bot.router.route(update, bot.api)
            except Exception:
                logger.exception("Ошибка обработки события {}", update.get("type"))


async def run() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)

    if not settings.vk_token:
        raise RuntimeError(
            "VK_TOKEN не задан. Скопируй .env.example в .env и заполни (см. README)."
        )
    if settings.bot_mode == "callback" and not settings.vk_confirmation_code:
        raise RuntimeError("Для режима callback нужен VK_CONFIRMATION_CODE (см. README).")

    bot = create_bot(settings)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    tick_engine = TickEngine(
        RedisActionStore(redis),
        pvp_window_seconds=settings.combat_tick_window_seconds,
        on_tick_resolved=combat_handlers.on_tick_resolved,
        on_battle_finished=combat_handlers.on_battle_finished,
    )
    tick_engine.start()
    combat_handlers.setup(tick_engine, bot.api)

    duel_engine = DuelEngine()
    duel_engine.start()

    travel_scheduler = PeerScheduler(world_handlers.handle_arrival, job_prefix="travel")
    travel_scheduler.start()
    explore_scheduler = PeerScheduler(world_handlers.handle_explore_done, job_prefix="explore")
    explore_scheduler.start()
    rest_scheduler = PeerScheduler(world_handlers.handle_rest_done, job_prefix="rest")
    rest_scheduler.start()
    world_handlers.setup(travel_scheduler, explore_scheduler, rest_scheduler, bot.api)

    # Авто-респавн: один общий батч-сканер мёртвых игроков (не задача-на-игрока)
    respawn_handlers.setup(bot.api, settings.respawn_live_countdown)
    combat_handlers.on_defeat_hook = respawn_handlers.register_death
    respawn_scheduler = AsyncIOScheduler()
    respawn_scheduler.add_job(
        respawn_handlers.scan, "interval", seconds=settings.respawn_scan_seconds, id="respawn_scan"
    )
    respawn_scheduler.start()

    # Callback API события маршрутизируются в vkbottle тем же путём,
    # каким их скармливает polling: bot.router.route(raw_event, api).
    app = create_app(settings, route_event=lambda event: bot.router.route(event, bot.api))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.host, settings.port)
    await site.start()
    logger.info("Сервер запущен: http://{}:{}{}", settings.host, settings.port, WEBHOOK_PATH)
    logger.info("Health-check:   http://{}:{}/health", settings.host, settings.port)

    try:
        if settings.bot_mode == "polling":
            await run_polling(bot)  # LongPoll-цикл вместо ожидания вебхуков
        else:
            await asyncio.Event().wait()  # события приходят в вебхук
    finally:
        respawn_scheduler.shutdown(wait=False)
        rest_scheduler.shutdown()
        explore_scheduler.shutdown()
        travel_scheduler.shutdown()
        duel_engine.shutdown()
        tick_engine.shutdown()
        await runner.cleanup()
        await redis.aclose()
        await dispose_engine()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка")
