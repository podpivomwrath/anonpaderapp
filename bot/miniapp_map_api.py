"""Карта мира в мини-аппе (патч 29): /api/miniapp/map/*.

Фронтенд считает тип локации/зону/расстояние САМ, детерминированно из
координат (см. game/world/location_types.py::_type_index — тот же хеш
воспроизведён в JS, см. miniapp/src/mapCatalog.js) — поэтому клетки НЕ
запрашиваются с сервера при каждом движении карты. С сервера тянется только
динамика (позиция/квест/маунты) плюс статичный каталог ОДИН раз при открытии
вкладки: города, зоны, типы локаций по региону.
"""

import random

from aiohttp import web
from sqlalchemy import select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.handlers import combat as combat_handlers
from bot.handlers import mounts as mounts_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import world as world_handlers
from bot.miniapp_auth import VK_USER_ID_KEY
from game.content_loader import load_location_types
from game.economy import fishing, mining
from game.economy import mining_config as mc
from game.world import grid
from game.world import world_config as wc
from models import Character, User
from services import (
    death_service,
    mining_service,
    mount_service,
    movement_service,
    story_service,
)

_rng = random.Random()


async def _load_character(session, vk_user_id: int) -> Character | None:
    return await session.scalar(
        select(Character)
        .join(User, User.id == Character.user_id)
        .where(User.vk_id == vk_user_id, Character.creation_state.is_(None))
    )


def _location_type_catalog() -> dict[str, list[dict]]:
    catalog: dict[str, list[dict]] = {}
    for type_def in load_location_types():
        catalog.setdefault(type_def.region, []).append({"id": type_def.id, "name": type_def.name})
    return catalog


_STATIC_CATALOG = {
    "bounds_min": wc.BOUNDS_MIN,
    "bounds_max": wc.BOUNDS_MAX,
    "city_coords": {region: [x, y] for region, (x, y) in wc.CITY_COORDS.items()},
    "zone_table": [[lo, hi, [lvl_lo, lvl_hi]] for lo, hi, (lvl_lo, lvl_hi) in wc.ZONE_TABLE],
    "location_types": _location_type_catalog(),
    # Патч 58: озёра — статика (фиксированные координаты), поэтому едут
    # тем же разовым каталогом, что города и зоны, а не запросом на
    # каждое движение карты.
    "lakes": [
        {"id": lake.id, "x": lake.x, "y": lake.y, "tier": lake.tier,
         "name": lake.name, "safe": fishing.is_safe_lake(lake.x, lake.y)}
        for lake in fishing.all_lakes()
    ],
    # Патч 59: рудники. Координаты статичны и едут каталогом, а вот СКОЛЬКО в
    # них руды — состояние мира, оно меняется постоянно и приходит отдельно, в
    # динамической части ответа (см. handle_get_state).
    "mines": [
        {"id": mine.id, "x": mine.x, "y": mine.y, "tier": mine.tier,
         "name": mine.name, "safe": mining.is_safe_mine(mine.x, mine.y)}
        for mine in mining.all_mines()
    ],
    "mine_ore_cap": mc.MINE_ORE_CAP,
}


async def handle_get_state(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await _load_character(db, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)

        foot_travel = None
        if movement_service.is_traveling(character):
            foot_travel = {
                "to_x": character.travel_target_x, "to_y": character.travel_target_y,
                "remaining_seconds": movement_service.remaining_seconds(character),
            }

        mount_travel = None
        travel_row = await mount_service.active_travel(db, character.id)
        if travel_row is not None:
            mount_travel = {
                "mount_id": travel_row.mount_id,
                "to_x": travel_row.to_x, "to_y": travel_row.to_y,
                "status": travel_row.status,
                "remaining_seconds": mount_service.frozen_remaining_seconds(travel_row)
                if travel_row.status == "ambushed"
                else mount_service.remaining_seconds(travel_row),
            }

        quest_target = None
        quest = await story_service.current_quest_def(db, character)
        if quest is not None and quest.target_x is not None and quest.target_y is not None:
            quest_target = {"x": quest.target_x, "y": quest.target_y, "label": quest.target_label}

        owned = await mount_service.owned_mounts(db, character.id)

        return web.json_response(
            {
                "pos_x": character.pos_x, "pos_y": character.pos_y,
                "is_dead": death_service.is_dead(character),
                "foot_travel": foot_travel,
                "mount_travel": mount_travel,
                "quest_target": quest_target,
                "mounts": [
                    {
                        "mount_id": m.mount_id, "name": m.name, "rarity": m.rarity, "emoji": m.emoji,
                        "seconds_per_cell": m.seconds_per_cell, "ambush_chance": m.ambush_chance,
                    }
                    for m in owned
                ],
                # Запас руды по рудникам — динамика, поэтому здесь, а не в
                # статичном каталоге: игрок видит, куда идти, до похода.
                "mine_ore": await mining_service.ore_counts(db),
                "catalog": _STATIC_CATALOG,
            }
        )


def _blocked_reason(character: Character, peer_id: int) -> str | None:
    """То же, что bot/handlers/mounts.py::_blocked_reason, но без гейта на
    пеший переход (карта не запрещает отправить маунт из чужого состояния,
    которое уже блокирует само по себе — movement_service ниже проверяется
    отдельно) и без world_handlers.is_busy на пешей ходьбе (учтено отдельным
    полем в ответе, а не блокировкой здесь)."""
    if death_service.is_dead(character):
        return "dead"
    if pvp_handlers.has_active_battle(peer_id):
        return "in_pvp"
    if combat_handlers.has_active_encounter(peer_id):
        return "in_combat"
    if world_handlers.is_busy(peer_id):
        return "busy"
    if movement_service.is_traveling(character):
        return "traveling_on_foot"
    # Патч 59: добыча блокирует всё, включая отправку маунта. Эта копия гейта
    # уже однажды разошлась с основной (bot/activity.py) — при добавлении
    # новой блокирующей активности правило надо продублировать и здесь.
    if mining_service.is_digging(character):
        return "mining"
    return None


async def handle_post_send_mount(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    mount_id = body.get("mount_id")
    x, y = body.get("x"), body.get("y")
    if not isinstance(mount_id, str) or not isinstance(x, int) or not isinstance(y, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await _load_character(db, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)

        reason = _blocked_reason(character, vk_user_id)
        if reason is not None:
            return web.json_response({"error": reason}, status=400)
        if await mount_service.active_travel(db, character.id) is not None:
            return web.json_response({"error": "already_on_mount"}, status=400)
        if not grid.in_bounds(x, y):
            return web.json_response({"error": "out_of_bounds"}, status=400)
        if (x, y) == (character.pos_x, character.pos_y):
            return web.json_response({"error": "already_there"}, status=400)
        owned = await mount_service.owned_mounts(db, character.id)
        if not any(m.mount_id == mount_id for m in owned):
            return web.json_response({"error": "mount_not_owned"}, status=400)

        # Тот же код, что и при отправке из чата (bot/handlers/mounts.py::
        # coord_input): запуск поездки и сообщение в чат — одна общая функция,
        # а не два похожих куска. Раньше карта повторяла эти шаги у себя, и
        # игрок, отправивший маунта с карты, не получал в чат ничего.
        seconds = await mounts_handlers.start_travel_and_notify(
            db, character, vk_user_id, mount_id, x, y
        )
        travel = await mount_service.active_travel(db, character.id)
        ambush_chance = mount_service.ambush_chance(mount_id)

    return web.json_response(
        {
            "travel_id": travel.id if travel is not None else None,
            "to_x": x, "to_y": y,
            "seconds": seconds,
            "ambush_chance": ambush_chance,
        }
    )


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/map/state", handle_get_state)
    app.router.add_post("/api/miniapp/map/send_mount", handle_post_send_mount)
