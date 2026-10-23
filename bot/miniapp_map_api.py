"""Карта мира в мини-аппе (патч 29): /api/miniapp/map/*.

Фронтенд считает тип локации/зону/расстояние САМ, детерминированно из
координат (см. game/world/location_types.py::_type_index — тот же хеш
воспроизведён в JS, см. miniapp/src/mapCatalog.js) — поэтому клетки НЕ
запрашиваются с сервера при каждом движении карты. С сервера тянется только
динамика (позиция/квест/маунты) плюс статичный каталог ОДИН раз при открытии
вкладки: города, зоны, типы локаций по региону.
"""

import random
from datetime import datetime, timezone

from aiohttp import web
from sqlalchemy import select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.handlers import mounts as mounts_handlers
from bot.miniapp_auth import VK_USER_ID_KEY
from game.content_loader import load_location_types
from game.economy import fishing, mining
from game.economy import fishing_config as fc
from game.economy import mining_config as mc
from game.economy import rift_config as rfc
from game.world import grid, scene_events, world_boss
from game.world import world_config as wc
from models import Character, User
from services import (
    death_service,
    mining_service,
    mount_service,
    movement_service,
    scene_event_service,
    story_service,
    world_boss_service,
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
    "world_radius": wc.WORLD_RADIUS,
    "bounds_min": wc.BOUNDS_MIN,
    "bounds_max": wc.BOUNDS_MAX,
    "city_coords": {region: [x, y] for region, (x, y) in wc.CITY_COORDS.items()},
    "zone_table": [[lo, hi, [lvl_lo, lvl_hi]] for lo, hi, (lvl_lo, lvl_hi) in wc.ZONE_TABLE],
    # Уровень мобов клетки (2026-10-15): тот же расчёт, что в игре -
    # mapCatalog.js::cellLevelRange повторяет world_config.cell_level_range.
    "mob_level_spread": wc.MOB_LEVEL_SPREAD,
    "city_safe_radius": wc.CITY_SAFE_RADIUS,
    "location_types": _location_type_catalog(),
    # Патч 58: озёра — статика (фиксированные координаты), поэтому едут
    # тем же разовым каталогом, что города и зоны, а не запросом на
    # каждое движение карты.
    "lakes": [
        {"id": lake.id, "x": lake.x, "y": lake.y, "tier": lake.tier,
         "name": lake.name, "safe": fishing.is_safe_lake(lake.x, lake.y),
         "need": fc.LAKE_REQUIRED_LEVEL.get(lake.tier, 1)}
        for lake in fishing.all_lakes()
    ],
    # Патч 59: рудники. Координаты статичны и едут каталогом, а вот СКОЛЬКО в
    # них руды — состояние мира, оно меняется постоянно и приходит отдельно, в
    # динамической части ответа (см. handle_get_state).
    "mines": [
        {"id": mine.id, "x": mine.x, "y": mine.y, "tier": mine.tier,
         "name": mine.name, "safe": mining.is_safe_mine(mine.x, mine.y),
         "need": mc.MINE_REQUIRED_LEVEL.get(mine.tier, 1)}
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
                # Движение по клеткам: карта ведёт значок по пути сама между
                # опросами. path - со стартовой клеткой, персонаж стоит на
                # path[cell_index]; paused - занят (бой, нападение), не едет.
                "path": [[travel_row.from_x, travel_row.from_y]]
                + [list(c) for c in mount_service.path_of(travel_row)],
                "cell_index": travel_row.cell_index,
                "step_seconds": travel_row.step_seconds,
                "next_cell_in": max(
                    (travel_row.next_cell_at.replace(tzinfo=travel_row.next_cell_at.tzinfo or timezone.utc)
                     - datetime.now(timezone.utc)).total_seconds(), 0.0,
                ) if travel_row.next_cell_at is not None else None,
                "paused": travel_row.status != "traveling" or mounts_handlers.is_paused(vk_user_id),
            }

        quest_target = None
        quest = await story_service.current_quest_def(db, character)
        if quest is not None and quest.target_x is not None and quest.target_y is not None:
            quest_target = {"x": quest.target_x, "y": quest.target_y, "label": quest.target_label}

        owned = await mount_service.owned_mounts(db, character.id)

        # Патч 110: след события - метка на карте, пока не остыл.
        trail_mark = None
        trail = await scene_event_service.get_trail(db, character.id)
        trail_def = scene_events.content().trails.get(trail.kind) if trail is not None else None
        if trail_def is not None and scene_event_service.trail_alive(trail):
            trail_mark = {"x": trail.x, "y": trail.y, "title": trail_def.title, "emoji": trail_def.emoji}

        # Патч 108: живой мировой босс - метка на карте.
        world_boss_mark = None
        boss = await world_boss_service.active_boss(db)
        if boss is not None:
            boss_def = world_boss.boss_def(boss.boss_id)
            world_boss_mark = {
                "x": boss.x, "y": boss.y, "ring": boss.ring, "level": boss.level,
                "name": boss_def.name if boss_def else "Мировой босс",
                "hp_percent": round(100 * boss.hp / boss.max_hp) if boss.max_hp else 0,
            }

        # Турбоишак дня (2026-10-19): где бегает сейчас.
        from services import turbo_ishak_service

        turbo = await turbo_ishak_service.active(db)
        turbo_mark = None
        if turbo is not None:
            x, y = turbo_ishak_service.current_cell(turbo)
            turbo_mark = {"x": x, "y": y, "running": False}
            run = turbo_ishak_service.run_view(turbo)
            if run is not None:
                # Как у маунта: карта ведёт значок по пути сама. Пути на карте
                # не рисуем - куда он бежит, игрок не видит.
                path, index, left = run
                turbo_mark.update({
                    "running": True, "path": [list(c) for c in path], "cell_index": index,
                    "step_seconds": turbo_ishak_service.step_seconds(), "next_cell_in": left,
                })

        # Курьер (2026-10-19): свой - пока бежит к тебе за посылкой, чужой - когда
        # уже бежит к тебе. Где он сейчас; путь не рисуем. С посылкой к получателю
        # свой курьер не виден (2026-10-21): он бежит прямо на получателя и ждёт
        # на его клетке - за 1 кусок руды выходил трекер любого игрока.
        from services import courier_service

        courier_marks = []
        mine = await courier_service.active_of(db, character.id)
        if mine is not None and mine.phase == courier_service.PICKUP:
            courier_marks.append({"x": mine.x, "y": mine.y, "own": True, "label": mine.label})
        for d in await courier_service.incoming(db, character.id):
            if mine is None or d.id != mine.id:
                courier_marks.append({"x": d.x, "y": d.y, "own": False, "label": d.label})

        # Гильдии: владения и закладки - цветом гильдии на карте.
        from services import guild_territory_service

        guild_cells = [
            {
                "x": cell.x, "y": cell.y, "tag": guild.tag, "guild_id": guild.id,
                "own": guild.id == character.guild_id, "status": cell.status,
                "base_tier": cell.base_tier, "mine": cell.mine_id is not None,
            }
            for cell, guild in await guild_territory_service.all_cells(db)
        ]

        # Разломы: видят все. Свободен / ждут у входа / внутри - для окна клетки.
        from services import rift_service

        rifts = []
        for r in await rift_service.active_rifts(db):
            t = rfc.RIFT_TYPES[r.kind]
            lo, hi = rfc.BANDS[r.ring]
            rifts.append({
                "x": r.x, "y": r.y, "name": t.name, "emoji": t.emoji, "hint": t.hint,
                "min_level": lo, "max_level": hi, "max_size": t.max_size,
                "minutes_left": rift_service.minutes_left(r), "state": r.state,
                "blood": rift_service.is_blood(r),
            })
        # Повозки торговой фирмы игрока: в пути - на клетке, где они сейчас.
        from services import trade_service

        # Заказы (2026-10-16): цели взятых заказов - там, где они сейчас (вне городов).
        from services import contract_service

        hunt_marks = []
        for target_id in await contract_service.hunted_ids(db, character.id):
            target = await db.get(Character, target_id)
            if target is not None and contract_service.visible_on_map(target):
                hunt_marks.append({"x": target.pos_x, "y": target.pos_y, "name": target.name, "level": target.level})
        cart_marks = []
        for cart in await trade_service.carts(db, character.id):
            x, y = trade_service.position(cart)
            cart_marks.append({"x": x, "y": y, "num": cart.slot, "traveling": cart.status == "traveling"})

        return web.json_response(
            {
                "pos_x": character.pos_x, "pos_y": character.pos_y,
                "guild_cells": guild_cells,
                "rifts": rifts,
                # Для окна клетки: хватает ли уровня у озера, рудника, разлома.
                "levels": {
                    "level": character.level, "fishing": character.fishing_level,
                    "mining": character.mining_level,
                },
                "carts": cart_marks,
                "hunts": hunt_marks,
                "is_dead": death_service.is_dead(character),
                "foot_travel": foot_travel,
                "mount_travel": mount_travel,
                "safe_route": bool((character.ui_flags or {}).get("safe_route")),
                "quest_target": quest_target,
                "world_boss": world_boss_mark,
                "turbo": turbo_mark,
                "couriers": courier_marks,
                "trail": trail_mark,
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


#: Код bot/busy.py -> код отказа, который понимает фронтенд (MapTab.jsx).
_MAP_REASONS = {
    "dead": "dead", "pvp": "in_pvp", "battle": "in_combat", "busy": "busy",
    "traveling_on_foot": "traveling_on_foot", "digging": "mining", "house_work": "house_work",
    "fishing": "fishing",
}


async def _blocked_reason(db, character: Character, peer_id: int) -> str | None:
    """Чем занят игрок - общая проверка bot/busy.py (2026-10-21). Раньше
    здесь была своя копия, и она не знала про групповой бой и рейд. Маунт
    в пути проверяется ниже отдельно (свой код already_on_mount)."""
    from bot.busy import busy

    found = await busy(db, character, peer_id, skip=("riding",), leaving=True)
    return _MAP_REASONS.get(found.code, "busy") if found is not None else None


async def handle_post_stop_travel(request: web.Request) -> web.Response:
    """Остановиться на текущей клетке пути - та же точка, что кнопка в чате
    (bot/handlers/mounts.py::stop_and_notify): в чат придёт экран клетки."""
    vk_user_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await _load_character(db, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        travel = await mount_service.active_travel(db, character.id)
        travel_id = travel.id if travel is not None else None
    if travel_id is None:
        return web.json_response({"error": "Ты сейчас не в пути."}, status=409)
    reason = await mounts_handlers.stop_and_notify(vk_user_id, travel_id)
    if reason is not None:
        return web.json_response({"error": reason}, status=409)
    return web.json_response({"ok": True})


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
    safe = body.get("safe") is True
    if not isinstance(mount_id, str) or not isinstance(x, int) or not isinstance(y, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await _load_character(db, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)

        reason = await _blocked_reason(db, character, vk_user_id)
        if reason is not None:
            return web.json_response({"error": reason}, status=400)
        from bot.busy import open_event

        if await open_event(vk_user_id) is not None:
            return web.json_response({"error": "in_event"}, status=400)
        if await mount_service.active_travel(db, character.id) is not None:
            return web.json_response({"error": "already_on_mount"}, status=400)
        if not grid.in_bounds(x, y):
            return web.json_response({"error": "out_of_bounds"}, status=400)
        if (x, y) == (character.pos_x, character.pos_y):
            return web.json_response({"error": "already_there"}, status=400)
        from services import pk_service

        if grid.city_region_at(x, y) is not None and pk_service.city_banned(character):
            return web.json_response({"error": "city_banned", "message": pk_service.CITY_BAN_TEXT}, status=400)
        owned = await mount_service.owned_mounts(db, character.id)
        if not any(m.mount_id == mount_id for m in owned):
            return web.json_response({"error": "mount_not_owned"}, status=400)

        # Тот же код, что и при отправке из чата (bot/handlers/mounts.py::
        # coord_input): запуск поездки и сообщение в чат — одна общая функция,
        # а не два похожих куска. Раньше карта повторяла эти шаги у себя, и
        # игрок, отправивший маунта с карты, не получал в чат ничего.
        seconds = await mounts_handlers.start_travel_and_notify(
            db, character, vk_user_id, mount_id, x, y, safe=safe,
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


async def handle_get_route(request: web.Request) -> web.Response:
    """Предпросмотр пути на карте: клетки и шанс нападения для каждого
    маунта. safe=1 - безопасный путь в обход колец опаснее цели."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        x, y = int(request.query["x"]), int(request.query["y"])
    except (KeyError, ValueError):
        return web.json_response({"error": "bad_request"}, status=400)
    safe = request.query.get("safe") == "1"
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await _load_character(db, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if not grid.in_bounds(x, y) or (x, y) == (character.pos_x, character.pos_y):
            return web.json_response({"error": "bad_request"}, status=400)
        fx, fy = character.pos_x, character.pos_y
        path = mount_service.route(fx, fy, x, y, safe)
        direct = mount_service.route(fx, fy, x, y, False) if safe else path
        owned = await mount_service.owned_mounts(db, character.id)
    return web.json_response({
        "cells": len(path),
        # Безопасный обход той же длины, что прямой (2026-10-20): время то же,
        # и окно говорит об этом прямо - иначе переключатель казался сломанным.
        "direct_cells": len(direct),
        "detour": path != direct,
        "path": [[fx, fy]] + [list(c) for c in path],
        "mounts": {
            m.mount_id: {
                "seconds": mount_service.total_travel_seconds(m.mount_id, len(path)),
                "ambush": mount_service.trip_ambush_chance(m.mount_id, fx, fy, x, y, path=path),
            }
            for m in owned
        },
    })


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/map/route", handle_get_route)
    app.router.add_get("/api/miniapp/map/state", handle_get_state)
    app.router.add_post("/api/miniapp/map/send_mount", handle_post_send_mount)
    app.router.add_post("/api/miniapp/map/stop_travel", handle_post_stop_travel)
