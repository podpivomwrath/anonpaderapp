"""Странная руна и Пепельный дракон (2026-11-12, владелец).

Руна в слоте питомца раз в час бормочет код (если хозяин был в игре за этот
час). Кто первым пришлёт этот код текстом, стоя у Монолита (0;0) с руной в
слоте, будит дракона: маунт, титул «Искатель» и объявление всем.

Подсказок нет нигде - ни в тексте руны, ни в справочнике, ни в ответе бота.
Неверный текст бот не читает вовсе (bot/button_gate.py): пропускается только
точный код, а дальше всё, что не сошлось (нет руны, не у Монолита, дракон
уже разбужен), тоже молчит - иначе ответ был бы подсказкой.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from bot import notices, pet_texts
from bot.background import spawn
from game.economy import pet_config as pc
from game.world import grid
from models import Character, User
from services import death_service, pet_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True
_bot_api = None
#: Код руны (pet_service.dragon_state). Держится в памяти, чтобы фильтр
#: набранного текста сверял его без похода в базу на каждое сообщение.
_code: str | None = None

ANNOUNCE_DELAY_SECONDS = 0.05


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def load_code() -> str:
    global _code
    async with get_session_factory()() as db:
        state = await pet_service.dragon_state(db)
        await db.commit()
        _code = state.code
    return _code


def is_code(text: str | None) -> bool:
    return bool(_code) and pet_service.normalize(text) == _code


class CodeTyped(ABCRule[Message]):
    """Прислан ровно код руны в личку (без кнопки и не командой)."""

    async def check(self, event: Message) -> bool:
        return not event.payload and event.peer_id == event.from_id and is_code(event.text)


@labeler.message(CodeTyped())
async def code_typed(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if (character is None or character.creation_state is not None
                or not pet_service.has_active(character, pc.RUNE)
                or not grid.is_monolith(character.pos_x, character.pos_y)
                or death_service.is_dead(character)):
            return
        if not await pet_service.claim_dragon(db, character):
            return
        name = character.name
        await db.commit()
    logger.info("Пепельный дракон разбужен: {} (vk {})", name, peer_id)
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=pet_texts.DRAGON_AWAKE, random_id=0,
                                     attachment=pet_texts.photo("dragon_awake"))
    except Exception:
        logger.exception("Дракон: не доставлено пробуждение {}", peer_id)
    spawn(announce(name, skip=peer_id))


async def announce(name: str, skip: int | None = None) -> int:
    """Объявление всем игрокам (кроме выключивших оповещения)."""
    async with get_session_factory()() as db:
        peers = (await db.scalars(
            select(User.vk_id).join(Character, Character.user_id == User.id)
            .where(Character.creation_state.is_(None), Character.is_banned.is_(False))
        )).all()
    text, photo = pet_texts.dragon_announce(name), pet_texts.photo("dragon_announce")
    sent = 0
    for vk_id in notices.keep([p for p in peers if p is not None and p != skip]):
        try:
            await _bot_api.messages.send(peer_id=vk_id, message=text, random_id=0, attachment=photo)
            sent += 1
        except Exception:
            logger.warning("Дракон: объявление не доставлено {}", vk_id)
        await asyncio.sleep(ANNOUNCE_DELAY_SECONDS)
    logger.info("Дракон: объявление доставлено {} из {}", sent, len(peers))
    return sent


async def rune_job() -> None:
    """Раз в час: руна бормочет код тем, кто держит её в слоте и был в игре."""
    if _bot_api is None:
        return
    code = _code or await load_code()
    since = datetime.now(timezone.utc) - timedelta(minutes=pc.RUNE_ACTIVE_MINUTES)
    async with get_session_factory()() as db:
        holders = await pet_service.holders(db, pc.RUNE)
    for character, vk_id in holders:
        seen = character.last_active_at
        if seen is None:
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if seen < since:
            continue
        try:
            await _bot_api.messages.send(peer_id=vk_id, message=pet_texts.rune_mutter(code), random_id=0)
        except Exception:
            logger.warning("Руна: не доставлено {}", vk_id)
