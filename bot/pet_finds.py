"""Что питомцы находят после исследования (2026-11-12): одна точка для всех
трёх исходов - событие (bot/handlers/explore.py), соло-победа
(bot/handlers/combat.py) и групповая победа (bot/handlers/group_combat.py).
Раньше горстка пепла жила тремя копиями в этих местах.

- Горстка пепла: без хорька - кнопка в чате, как раньше; с хорьком кнопки
  нет, он раскапывает сам и сразу присылает находку.
- Пепельный плетельщик: иногда приносит из сети реликвию; сам он иногда
  выпадает с победы над тварью Обетованного Кряжа (won).

Зовётся после сводки клетки: сообщения находок идут под ней.
"""

from __future__ import annotations

import random

from loguru import logger

from bot import ash_handful_state, pet_texts
from game.economy import pet_config as pc
from game.world.location_types import region_for
from models import Character
from services import ash_service, trophy_service
from services.db import get_session_factory


async def after_explore(
    peer_id: int, character_id: int, cell: tuple[int, int] | None, rng: random.Random, won: bool = False,
) -> None:
    from bot.handlers import explore, world  # цикл импортов
    from bot.keyboards.world import ASH_OFFER_TEXT, ash_handful_keyboard

    async with get_session_factory()() as db:
        character = await db.get(Character, character_id)
        pet = character.pet_id if character is not None else None
        vk_id = None
        if pet == pc.FERRET:
            from services import onboarding_service

            vk_id = await onboarding_service.vk_id_for_character(db, character_id)

    if ash_service.roll_appears(rng):
        if pet == pc.FERRET and vk_id is not None:
            await explore.dig_ash(peer_id, vk_id, pet_texts.FERRET_DIG)
        else:
            ash_handful_state.mark(peer_id, cell)
            await _send(world._bot_api, peer_id, ASH_OFFER_TEXT, keyboard=ash_handful_keyboard())

    if pet == pc.SPIDER and rng.random() < pc.SPIDER_CATCH_CHANCE:
        async with get_session_factory()() as db:
            character = await db.get(Character, character_id)
            drop = await trophy_service.grant_from_event(db, character, rng)
            await db.commit()
        line = trophy_service.format_drop_line(drop, source="spider")
        if line:
            await _send(world._bot_api, peer_id, line)

    if won and cell is not None and region_for(*cell) == pc.SPIDER_REGION and rng.random() < pc.SPIDER_DROP_CHANCE:
        await grant_and_tell(world._bot_api, peer_id, character_id, pc.SPIDER)


async def grant_and_tell(api, peer_id: int, character_id: int, pet_id: str) -> bool:
    """Выдать питомца и прислать сцену находки. False - он уже был."""
    from services import pet_service

    async with get_session_factory()() as db:
        character = await db.get(Character, character_id)
        if character is None or not await pet_service.grant(db, character, pet_id):
            return False
        await db.commit()
    text, photo = FOUND[pet_id]
    await _send(api, peer_id, text, attachment=pet_texts.photo(photo))
    return True


FOUND = {
    pc.SPIDER: (pet_texts.SPIDER_FOUND, "spider"),
    pc.HOUND: (pet_texts.HOUND_FOUND, "hound"),
    pc.RUNE: (pet_texts.RUNE_FOUND, "rune"),
}


async def _send(api, peer_id: int, text: str, **kw) -> None:
    if api is None:
        return
    try:
        await api.messages.send(peer_id=peer_id, message=text, random_id=0, **kw)
    except Exception:
        logger.warning("Находка питомца не доставлена {}", peer_id)
