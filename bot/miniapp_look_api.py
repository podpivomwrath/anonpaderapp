"""Окно чужого игрока (2026-11-14, владелец): нажал на имя в топе или на
доске - небольшое окно с силуэтом, надетыми вещами и рунами.

Только то, что на нём надето. Владелец отдельно: «никакой лишней информации
по типу инвентаря игрока или его страницы» - поэтому здесь нет сумки, рун в
сумке, золота, места на карте, vk id и ссылки на страницу. Питомца тоже нет:
он не вещь и не руна. Новые поля сюда - только с тем же правилом.
"""

from aiohttp import web
from sqlalchemy import select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from bot.miniapp_runes_api import PLACE_TITLES
from game.economy import ability_config as ac
from game.economy import runes as runes_math
from game.economy import runes_config as rc
from models import Character, Inventory, Item
from services import (
    admin_service,
    item_service,
    naming,
    ring_slot_service,
    rune_service,
    title_service,
)


def _rune(rune_id: str | None, known: dict[str, int]) -> dict | None:
    rune_def = rc.BY_ID.get(rune_id) if rune_id else None
    if rune_def is None:
        return None
    absorbed = known.get(rune_id, 0)
    return {
        "id": rune_def.id, "kind": rune_def.kind, "name": rune_def.name, "rarity": rune_def.rarity,
        "rarity_title": rc.RARITY_TITLES[rune_def.rarity],
        "efficiency": round(runes_math.efficiency(rune_def.curve, absorbed) * 100, 1),
    }


async def look_payload(db, target: Character) -> dict:
    rows = (await db.execute(
        select(Item).join(Inventory, Inventory.item_id == Item.id)
        .where(Inventory.character_id == target.id, Inventory.equipped.is_(True))
    )).scalars().all()
    items = [
        {
            "slot": item.slot, "name": item_service.display_name(item), "icon": naming.item_icon_key(item),
            "rarity": item.rarity, "rarity_title": naming.rarity_title(item.rarity),
            "ilvl": item.ilvl, "enchant": item.enchant_level or 0, "base_stats": item.base_stats,
        }
        for item in rows
    ]
    ring = ring_slot_service.worn(target)
    ring_info = ring_slot_service._info(ring) if ring else None

    known = await rune_service.mastery(db, target.id)
    taken = {(r.kind, r.slot): r.rune_id for r in await rune_service.slots(db, target.id)}
    hero = [_rune(taken.get((rc.HERO, str(i))), known) for i in range(target.rune_hero_slots)]
    abilities = []
    for i in range(rc.ABILITY_SLOTS):
        rune_id = taken.get((rc.ABILITY, str(i)))
        if not rune_id or rune_id not in ac.BY_ID:
            continue
        abilities.append({
            "rune": _rune(rune_id, known),
            "step": ac.step_of(rune_id, known.get(rune_id, 0)),
            "facets": [r for r in (_rune(taken.get((rc.SKILL, f"{rune_id}:{n}")), known) for n in (0, 1)) if r],
        })
    gear = []
    for place in rc.GEAR_PLACES:
        worn = [r for r in (_rune(taken.get((rc.GEAR, f"{place}:{i}")), known)
                            for i in range(rc.GEAR_SLOTS_PER_PLACE)) if r]
        if worn:
            gear.append({"title": PLACE_TITLES[place], "runes": worn})

    return {
        "name": target.name, "level": target.level,
        "base_class": target.base_class, "subclass": target.subclass, "gender": target.gender,
        "class_title": admin_service.class_title(target),
        "title": title_service.name_of(target.active_title_id) if target.active_title_id else None,
        "title_tier": title_service.tier_of(target.active_title_id),
        "items": items, "ring": ring_info,
        "runes": {"hero": [r for r in hero if r], "abilities": abilities, "gear": gear},
    }


async def handle_get_look(request: web.Request) -> web.Response:
    try:
        target_id = int(request.query["id"])
    except (KeyError, ValueError):
        return web.json_response({"error": "bad_request"}, status=400)
    _ = request[VK_USER_ID_KEY]  # только проверенный игрок мини-аппа
    async with request.app[SESSION_FACTORY_KEY]() as db:
        target = await db.get(Character, target_id)
        if target is None or target.creation_state is not None:
            return web.json_response({"error": "not_found"}, status=404)
        return web.json_response(await look_payload(db, target))


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/look", handle_get_look)
