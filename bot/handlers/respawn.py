"""Авто-респавн (combat-patch-2, п.5): один общий батч-сканер, НЕ задача-на-игрока.

Экономно: единственный периодический job (APScheduler interval) сканирует БД на
мёртвых игроков и:
  - возрождает тех, у кого таймер вышел (HP полное, город региона, меню города);
  - при RESPAWN_LIVE_COUNTDOWN — раз в скан обновляет сообщение о смерти остатком
    времени (edit). Боевые сообщения по частоте не трогаются — обновления таймера
    идут отдельным низкочастотным сканом.
Если упор в rate limit VK — RESPAWN_LIVE_COUNTDOWN=False: статичное сообщение.
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from bot.keyboards import world as kb
from bot.onboarding_texts import REGION_TITLES
from game.world import flavor
from game.world import world_config as wc
from models import Character, User
from services import death_service, vitals_service
from services.db import get_session_factory

_bot_api = None
_live_countdown = True
# peer_id -> conversation_message_id сообщения о смерти (для edit-отсчёта)
_death_message: dict[int, int] = {}


def setup(bot_api, live_countdown: bool) -> None:
    global _bot_api, _live_countdown
    _bot_api = bot_api
    _live_countdown = live_countdown


def _death_text(respawn_at: datetime, now: datetime, xp_lost: int = 0) -> str:
    text = flavor.death_line()
    if xp_lost > 0:
        text += "\n" + flavor.death_penalty_line(xp_lost)
    if _live_countdown and respawn_at is not None:
        left = max(0, (respawn_at - now).total_seconds())
        if left >= 60:
            text += f"\n\nДо возрождения: ~{left / 60:.0f} мин."
        else:
            text += f"\n\nДо возрождения: ~{int(left)} сек."
    else:
        text += "\n\nВозрождение скоро."
    return text


async def register_death(peer_id: int, respawn_at: datetime, xp_lost: int = 0) -> None:
    """Смерть игрока: убрать кнопки, показать атмосферный текст (+ штраф опыта)."""
    now = datetime.now(timezone.utc)
    resp = await _bot_api.messages.send(
        peer_id=peer_id, message=_death_text(respawn_at, now, xp_lost), random_id=0,
        keyboard=kb.waiting_keyboard(),
    )
    # vkbottle messages.send возвращает conversation_message_id (или message_id)
    try:
        _death_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


async def scan() -> None:
    """Батч-проход: возродить готовых, обновить отсчёт остальным. Один job на всех."""
    if _bot_api is None:
        return
    now = datetime.now(timezone.utc)
    sf = get_session_factory()
    to_revive: list[tuple[int, str]] = []
    to_update: list[tuple[int, datetime]] = []
    async with sf() as db:
        rows = (
            await db.execute(
                select(Character, User.vk_id)
                .join(User, User.id == Character.user_id)
                .where(Character.respawn_at.isnot(None))
            )
        ).all()
        for character, vk_id in rows:
            if not death_service.is_dead(character, now):
                # таймер вышел — возрождаем
                death_service.respawn_if_ready(character, now)
                vitals_service.restore_full(character)
                character.pos_x, character.pos_y = wc.CITY_COORDS[character.region]
                to_revive.append((vk_id, character.region))
            else:
                to_update.append((vk_id, character.respawn_at))
        await db.commit()

    for peer_id, region in to_revive:
        _death_message.pop(peer_id, None)
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=flavor.respawn_line(REGION_TITLES[region]),
            random_id=0,
            keyboard=kb.city_menu_keyboard(),
        )

    if _live_countdown:
        for peer_id, respawn_at in to_update:
            msg_id = _death_message.get(peer_id)
            if msg_id is None:
                continue
            try:
                await _bot_api.messages.edit(
                    peer_id=peer_id,
                    conversation_message_id=msg_id,
                    message=_death_text(respawn_at, now),
                )
            except Exception:
                logger.debug("Не удалось обновить отсчёт респавна для {}", peer_id)
