"""Ворон (питомец, 2026-11-12): пишет хозяину, когда рядом появляется игрок -
на его клетке или на соседней.

Один обход на всех раз в RAVEN_SCAN_SECONDS: воронов единицы (тройка
лучших сезона PvP), и следить за каждым шагом каждого игрока ради них
дороже, чем раз в 15 секунд оглядеться вокруг каждого ворона. Об одном и
том же игроке ворон молчит RAVEN_REPEAT_MINUTES.

Не считаются: своя группа и гильдия, ушедшие в долгий путь, спустившиеся в
руины, летящие на драконе, мёртвые и отошедшие от игры (АФК - как в
«Осмотреться»), стоящие в городе. Хозяин в городе или сам АФК - ворон молчит.
"""

from __future__ import annotations

import time

from loguru import logger
from sqlalchemy import select

from bot import pet_texts
from game.economy import pet_config as pc
from game.world import grid
from models import Character, CharacterVoyage, GroupMember
from services import (
    death_service,
    mount_service,
    pet_service,
    pvp_service,
    ruins_service,
)
from services.db import get_session_factory

_bot_api = None

#: id хозяина ворона -> {id замеченного игрока: когда о нём написали (time.time())}
_seen: dict[int, dict[int, float]] = {}


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _forget_old(now: float) -> None:
    limit = now - pc.RAVEN_REPEAT_MINUTES * 60
    for owner_id in list(_seen):
        marks = {cid: t for cid, t in _seen[owner_id].items() if t > limit}
        if marks:
            _seen[owner_id] = marks
        else:
            del _seen[owner_id]


def fresh(owner_id: int, others: list[int], now: float) -> list[int]:
    """Кого ворон ещё не называл за RAVEN_REPEAT_MINUTES; отмечает их."""
    marks = _seen.setdefault(owner_id, {})
    limit = now - pc.RAVEN_REPEAT_MINUTES * 60
    new = [cid for cid in others if marks.get(cid, 0) <= limit]
    for cid in new:
        marks[cid] = now
    return new


async def _group_ids(db, character_id: int) -> set[int]:
    group_id = await db.scalar(select(GroupMember.group_id).where(GroupMember.character_id == character_id))
    if group_id is None:
        return set()
    return set((await db.scalars(select(GroupMember.character_id).where(GroupMember.group_id == group_id))).all())


async def scan() -> None:
    if _bot_api is None:
        return
    now = time.time()
    _forget_old(now)
    messages: list[tuple[int, str]] = []
    async with get_session_factory()() as db:
        owners = await pet_service.holders(db, pc.RAVEN)
        if not owners:
            return
        hidden = set((await db.scalars(ruins_service.inside_query())).all())
        hidden |= set((await db.scalars(mount_service.flying_query())).all())
        hidden |= set((await db.scalars(
            select(CharacterVoyage.character_id).where(CharacterVoyage.status == "away"))).all())
        r = pc.RAVEN_RADIUS
        for owner, vk_id in owners:
            x, y = owner.pos_x, owner.pos_y
            if (owner.id in hidden or pvp_service.is_afk(owner) or death_service.is_dead(owner)
                    or grid.city_region_at(x, y) is not None):
                continue
            rows = (await db.scalars(select(Character).where(
                Character.pos_x.between(x - r, x + r), Character.pos_y.between(y - r, y + r),
                Character.id != owner.id, Character.creation_state.is_(None),
            ).order_by(Character.id))).all()
            friends = await _group_ids(db, owner.id)
            near = [
                c for c in rows
                if c.id not in hidden and c.id not in friends
                and (owner.guild_id is None or c.guild_id != owner.guild_id)
                and grid.city_region_at(c.pos_x, c.pos_y) is None
                and not death_service.is_dead(c) and not pvp_service.is_afk(c)
            ]
            new = set(fresh(owner.id, [c.id for c in near], now))
            lines = [
                pet_texts.raven_line(c.name, pvp_service.class_title(c), c.level, c.pos_x - x, c.pos_y - y)
                for c in near if c.id in new
            ]
            if lines:
                messages.append((vk_id, pet_texts.raven_message(lines)))
    for vk_id, text in messages:
        try:
            await _bot_api.messages.send(peer_id=vk_id, message=text, random_id=0)
        except Exception:
            logger.warning("Ворон: не доставлено {}", vk_id)
