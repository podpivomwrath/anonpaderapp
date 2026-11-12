"""Топ руин: итог недели в ночь на понедельник по Москве (2026-11-13).
Правила и выдача - services/ruins_top_service.py, здесь только запуск и
сообщения призёрам."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from models import Character, User
from services import ruins_top_service
from services.db import get_session_factory

_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def week_job() -> None:
    """Повторный вызов ничего не делает - неделя уже подведена."""
    try:
        async with get_session_factory()() as db:
            awards = await ruins_top_service.close_week(db)
            ids = [a.character_id for a in awards]
            peers = dict((await db.execute(
                select(Character.id, User.vk_id).join(User, User.id == Character.user_id).where(Character.id.in_(ids))
            )).all()) if ids else {}
            await db.commit()
    except Exception:
        logger.exception("Топ руин: итог недели не подведён")
        return
    if awards:
        logger.info("Топ руин: итог недели, призёров {}", len(awards))
    if _bot_api is None:
        return
    for award in awards:
        peer_id = peers.get(award.character_id)
        if peer_id is None:
            continue
        try:
            await _bot_api.messages.send(peer_id=peer_id, message=ruins_top_service.award_text(award), random_id=0)
        except Exception:
            logger.exception("Топ руин: весть об итогах не доставлена {}", peer_id)
