"""Торговые фирмы: фоновый тик прибытия повозок и вести игроку.

Управление фирмой - только в мини-аппе (вкладка «Фракция»,
bot/miniapp_trade_api.py); здесь - доставка повозок и короткое сообщение
о прибытии (если игрок его не отключил).
"""

import random

from game import plural
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


async def _peers(db, ids) -> dict[int, int]:
    if not ids:
        return {}
    return dict((await db.execute(
        select(Character.id, User.vk_id).join(User, User.id == Character.user_id).where(Character.id.in_(ids))
    )).all())


async def order_job() -> None:
    """Срочные заказы: изредка появляется новый; включившим вести - сообщение."""
    try:
        async with get_session_factory()() as db:
            order = await trade_service.order_tick(db, _rng)
            peers = {}
            if order is not None:
                peers = await _peers(db, await trade_service.order_subscribers(db))
                text = trade_service.order_text(order)
            await db.commit()
    except Exception:
        logger.exception("Торговля: заказ не появился")
        return
    if order is None:
        return
    logger.info("Торговля: срочный заказ {} в {} ({} ящ.)", order.good_id, order.city, order.total)
    if _bot_api is None:
        return
    for peer_id in peers.values():
        try:
            await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0)
        except Exception:
            logger.exception("Торговля: весть о заказе не доставлена {}", peer_id)


_PLACE = {1: "первый", 2: "второй", 3: "третий"}
_CHEST_NAMES = {"ashen": "Пепельный ларец", "ore": "Ларец руды", "supply": "Ларец расходников"}


def week_award_text(award) -> str:
    from bot.onboarding_texts import REGION_TITLES

    chests = ", ".join(f"{_CHEST_NAMES[k]} ×{n}" for k, n in award.chests.items())
    text = (
        f"🏆 Итоги недели: ты {_PLACE[award.place]} поставщик фракции {REGION_TITLES[award.city]}. "
        f"Награда: {chests}."
    )
    if award.place == 1:
        text += " Всю эту неделю тебе идёт доля налога с переводов игрокам твоей фракции."
    return text


async def week_job() -> None:
    """Понедельник по Москве: итоги прошлой недели фракций (повторно - ничего)."""
    from services import faction_service

    try:
        async with get_session_factory()() as db:
            awards = await faction_service.close_week(db)
            peers = await _peers(db, {a.character_id for a in awards})
            await db.commit()
    except Exception:
        logger.exception("Фракции: итог недели не подведён")
        return
    if awards:
        logger.info("Фракции: итог недели, наград {}", len(awards))
    if _bot_api is None:
        return
    for award in awards:
        peer_id = peers.get(award.character_id)
        if peer_id is None:
            continue
        try:
            await _bot_api.messages.send(peer_id=peer_id, message=week_award_text(award), random_id=0)
        except Exception:
            logger.exception("Фракции: весть об итогах не доставлена {}", peer_id)


def payout_text(payout) -> str:
    parts = []
    if payout.gold:
        parts.append(f"{payout.gold} золота")
    if payout.gems:
        parts.append(plural.gems(payout.gems))
    return (
        f"🏆 Доля первого поставщика за сутки: {' и '.join(parts)} - из налога с переводов игрокам твоей фракции."
    )


async def payout_job() -> None:
    """Раз в сутки по Москве: накопленные доли налога - первым поставщикам."""
    from services import faction_service

    try:
        async with get_session_factory()() as db:
            payouts = await faction_service.pay_leaders(db)
            peers = await _peers(db, {p.character_id for p in payouts})
            await db.commit()
    except Exception:
        logger.exception("Фракции: доля налога не выплачена")
        return
    if _bot_api is None:
        return
    for payout in payouts:
        peer_id = peers.get(payout.character_id)
        if peer_id is None:
            continue
        try:
            await _bot_api.messages.send(peer_id=peer_id, message=payout_text(payout), random_id=0)
        except Exception:
            logger.exception("Фракции: весть о доле не доставлена {}", peer_id)
