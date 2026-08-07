"""Точка входа: aiohttp-сервер (Callback API) + vkbottle + тик-движок."""

import asyncio
import sys

import redis.asyncio as aioredis
from aiohttp import web
from loguru import logger
from vkbottle import Bot

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.handlers import LABELERS, list_keeper, onboarding
from bot.handlers import appraiser as appraiser_handlers
from bot.handlers import combat as combat_handlers
from bot.handlers import elixir_shop as elixir_shop_handlers
from bot.handlers import inventory as inventory_handlers
from bot.handlers import moderation as moderation_handlers
from bot.handlers import mounts as mounts_handlers
from bot.handlers import presets as presets_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window as stats_window_handlers
from bot.handlers import world as world_handlers
from bot.webhook import WEBHOOK_PATH, create_app
from config import Settings, get_settings
from game.combat import balance_config as bc
from game.combat.duel_engine import DuelEngine
from game.combat.tick_engine import InMemoryActionStore, RedisActionStore, TickEngine
from game.economy import mount_config as mc
from game.world.scheduler import PeerScheduler
from services.db import dispose_engine


def create_bot(settings: Settings) -> Bot:
    bot = Bot(token=settings.vk_token)
    for labeler in LABELERS:
        bot.labeler.load(labeler)
    moderation_handlers.setup_middleware(bot)  # патч 27: бан-гейт РАНЬШЕ всех остальных middleware
    onboarding.setup(bot)  # диспенсер состояний + восстановление FSM из БД
    list_keeper.setup(bot)  # патч 12: FSM выбора подкласса + восстановление
    mounts_handlers.setup(bot, bot.api, settings.respawn_live_countdown)  # патч 25, п.7: FSM координат
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
    stats_window_handlers.setup(bot.api)
    appraiser_handlers.setup(bot.api)
    inventory_handlers.setup(bot.api)
    presets_handlers.setup(bot.api)
    elixir_shop_handlers.setup(bot.api)
    moderation_handlers.setup(bot.api)  # патч 27: ЛС администратору с /баг-репортами

    # Открытое PvP (патч 22): дуэль (последовательные ходы) + массовый бой
    # (одновременный резолв) — ОТДЕЛЬНЫЕ движки от PvE tick_engine выше:
    # там PLAYER_ID=1/MOB_ID=2 фиксированы под одного игрока и одного моба,
    # здесь комбатанты — реальные character.id, участников может быть много.
    # Реестр боёв (bot/handlers/pvp.py) целиком в памяти — как и у duel_engine,
    # поэтому массовому PvP тоже достаточно InMemoryActionStore, без Redis.
    duel_engine = DuelEngine(
        on_turn_resolved=pvp_handlers.on_duel_turn_resolved,
        on_duel_finished=pvp_handlers.on_duel_finished,
        max_turns=bc.PVP_MAX_TURNS,
    )
    duel_engine.start()

    pvp_tick_engine = TickEngine(
        InMemoryActionStore(),
        on_tick_resolved=pvp_handlers.on_mass_tick_resolved,
        on_battle_finished=pvp_handlers.on_mass_battle_finished,
        max_turns=bc.PVP_MAX_TURNS,
    )
    pvp_tick_engine.start()
    pvp_handlers.setup(duel_engine, pvp_tick_engine, bot.api)

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

    # Маунты (патч 25, п.7): нападения/прибытия/live-отсчёт — свой job,
    # интервал из game/economy/mount_config.py (игровая тонкая настройка, не
    # деплой-параметр окружения, поэтому не в Settings).
    mount_scheduler = AsyncIOScheduler()
    mount_scheduler.add_job(
        mounts_handlers.scan, "interval", seconds=mc.TRAVEL_COUNTDOWN_UPDATE_SECONDS, id="mount_scan",
    )
    mount_scheduler.start()

    # Callback API события маршрутизируются в vkbottle тем же путём,
    # каким их скармливает polling: bot.router.route(raw_event, api).
    app = create_app(settings, route_event=lambda event: bot.router.route(event, bot.api), redis=redis)

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
        mount_scheduler.shutdown(wait=False)
        respawn_scheduler.shutdown(wait=False)
        rest_scheduler.shutdown()
        explore_scheduler.shutdown()
        travel_scheduler.shutdown()
        duel_engine.shutdown()
        pvp_tick_engine.shutdown()
        tick_engine.shutdown()
        await runner.cleanup()
        await redis.aclose()
        await dispose_engine()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка")
