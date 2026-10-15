"""Торговые фирмы: фоновый тик прибытия повозок и вести игроку.

Управление фирмой - только в мини-аппе (вкладка «Фракция»,
bot/miniapp_trade_api.py); здесь - доставка повозок и короткое сообщение
о прибытии (если игрок его не отключил).
"""

import random

from loguru import logger
from sqlalchemy import select

from models import Character, User
from services import trade_service
from services.db import get_session_factory

_bot_api = None
_rng = random.Random()

#: Как часто проверять повозки, чьё время пришло.
TICK_SECONDS = 15


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def tick_job() -> None:
    try:
        async with get_session_factory()() as db:
            arrivals = await trade_service.tick(db, _rng)
            peers = {}
            if arrivals:
                ids = {a.character_id for a in arrivals}
                peers = dict((await db.execute(
                    select(Character.id, User.vk_id).join(User, User.id == Character.user_id)
                    .where(Character.id.in_(ids))
                )).all())
            await db.commit()
    except Exception:
        logger.exception("Торговля: тик прибытия не прошёл")
        return
    if _bot_api is None:
        return
    from bot.handlers import stats_window

    for arrival in arrivals:
        peer_id = peers.get(arrival.character_id)
        if peer_id is None:
            continue
        try:
            if arrival.notify:
                await _bot_api.messages.send(peer_id=peer_id, message=arrival.text(), random_id=0)
            levelup = arrival.char_levelup
            if levelup is not None and levelup.levels_gained:
                await stats_window.notify_levelup(peer_id, levelup.levels_gained, levelup.new_level)
        except Exception:
            logger.exception("Торговля: весть о прибытии не доставлена {}", peer_id)
