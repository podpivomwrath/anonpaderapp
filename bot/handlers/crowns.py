"""Венец топ-1 (патч 91): суточный пересчёт и весть о потере.

Здесь живёт только доставка. Кто держит доску и что ему за это — в
services/crown_service.py; сервис сообщений не шлёт и про ВК не знает, тот же
порядок, что у остальных проактивных уведомлений.

Почему раз в сутки, а не вживую: движок боя берёт характеристики на старте
сессии, и смена венца на третьем тике рассинхронила бы бой с тем, что игрок
видит. К тому же при восемнадцати игроках живой пересчёт мигал бы по
нескольку раз за вечер, а весть о потере превратилась бы в спам.
"""

from loguru import logger
from sqlalchemy import select

from game.economy import crown_config as cc
from models import Character, User
from services import crown_service, leaderboard_service
from services.db import get_session_factory

_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def lost_crown_text(board: str, successor_name: str | None) -> str:
    title = cc.CROWN_TITLES.get(board, board)
    board_title = leaderboard_service.BOARD_TITLES.get(board, board)
    effect = cc.CROWN_EFFECTS.get(board, "")
    if successor_name:
        who = f"Первым в топе «{board_title}» теперь {successor_name}."
    else:
        who = f"Первого в топе «{board_title}» больше нет."
    return (
        f"Венец «{title}» больше не твой.\n\n"
        f"{who}\n\n"
        f"Рамка снята, {effect} больше не действует. Вернёшь место - вернётся и венец."
    )


async def _peer_ids(db, character_ids: list[int]) -> dict[int, int]:
    if not character_ids:
        return {}
    rows = (
        await db.execute(
            select(Character.id, User.vk_id)
            .join(User, User.id == Character.user_id)
            .where(Character.id.in_(character_ids))
        )
    ).all()
    return {character_id: vk_id for character_id, vk_id in rows}


async def recompute_and_notify() -> None:
    """Суточная сверка венцов. Вызывается планировщиком."""
    try:
        async with get_session_factory()() as db:
            displaced = await crown_service.recompute(db)
            peers = await _peer_ids(db, [d.character_id for d in displaced])
            await db.commit()
    except Exception:
        logger.exception("Не удалось пересчитать венцы топов")
        return

    for loss in displaced:
        peer_id = peers.get(loss.character_id)
        if peer_id is None:
            continue
        try:
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=lost_crown_text(loss.board, loss.successor_name),
                random_id=0,
            )
        except Exception:
            # Дальше по списку, а не выход: чаще всего это «заблокировал
            # бота», и из-за одного молчуна остальные не должны остаться без
            # вести о том, что их бонус кончился.
            logger.exception("Не удалось известить о потере венца: {}", loss.character_id)
