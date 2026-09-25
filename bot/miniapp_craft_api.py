"""Эндпоинты мастерской (патч 72): /api/miniapp/craft/*.

Крафт живёт ТОЛЬКО в мини-аппе — в чате его нет. Причина не в лени: выбор
специализации, руды по двум осям и ступени процентов — это таблица, а не
разговор, и в клавиатуре ВК она не помещается без пагинации на три экрана.

Личность игрока приходит из request[VK_USER_ID_KEY], положенного
miniapp_auth_middleware после проверки подписи — тело запроса на это не
влияет никогда.
"""

import random

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import craft_config as cc
from game.economy import crafting, mining
from models import Character, Item
from services import craft_service, item_service, naming
from services import onboarding_service as onboarding_svc

_rng = random.Random()


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _spec_payload(source_id: str) -> list[dict]:
    """Три варианта ковки с их предрасположенностью.

    Числа не отдаём сознательно: игрок видит, КУДА целится специализация, но
    не что именно выпадет. Веса нормируем в доли от максимального — клиенту
    нужно рисовать полоски, а не воспроизводить формулу (однажды мини-апп уже
    пересказывал серверное правило своими словами и врал, см. патч 57).
    """
    recipe = crafting.recipe_for(source_id)
    result = []
    for spec in cc.SPECS:
        weights = cc.SPEC_WEIGHTS[spec]
        top = max(weights.values())
        result.append({
            "id": spec,
            "title": cc.SPEC_TITLES[spec],
            "name": recipe.outputs[spec].name if recipe else spec,
            "flavor": recipe.outputs[spec].flavor if recipe else "",
            "lean": [
                {"stat": stat, "share": round(weight / top, 3)}
                for stat, weight in sorted(weights.items(), key=lambda kv: -kv[1])
            ],
        })
    return result


def _item_payload(character: Character, item: Item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "slot": item.slot,
        "icon": naming.item_icon_key(item),
        # Редкость нужна интерфейсу для свечения рамки (патч 79).
        "rarity": item.rarity,
        "stats": item.base_stats or {},
        "spec": item.craft_spec,
        "spec_title": cc.SPEC_TITLES.get(item.craft_spec) if item.craft_spec else None,
        "efficiency": item.craft_efficiency,
        "next_efficiency": (
            crafting.next_efficiency(item.craft_efficiency)
            if item.craft_efficiency is not None else None
        ),
        "recrafts": item.craft_recrafts,
        "bound": item.bound,
        "source_id": item.craft_source_id,
        # Цена СЛЕДУЮЩЕЙ операции — считает сервер, клиент только показывает.
        # Через craft_service, а не по конфигу напрямую: там же живёт скидка
        # венца, и показанная цена обязана совпадать со списанной.
        "next_craft_cost": craft_service.recraft_cost(character, item),
    }


async def handle_get_craft(request: web.Request) -> web.Response:
    """Всё, что нужно мастерской, одним запросом: предметы, руда, инструменты."""
    vk_user_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)

        items = [
            _item_payload(character, item)
            for item, _equipped in await item_service.get_inventory(db, character.id)
            if crafting.is_craftable(item.craft_source_id)
        ]
        ore = [
            {
                "id": definition.id,
                "name": definition.name,
                "emoji": definition.emoji,
                "tier": definition.tier,
                "grade": grade_id,
                "grade_name": mining.grade_name(grade_id),
                "count": count,
                "craft_efficiency": (
                    cc.craft_efficiency_for(definition.tier)
                    if definition.tier <= cc.CRAFT_MAX_ORE_TIER else None
                ),
                "tool_ceiling": crafting.tool_ceiling_for(definition.tier),
                "craft_cost": craft_service.first_craft_cost(character),
                "tool_cost": (
                    craft_service.tool_cost(
                        character, crafting.tool_ceiling_for(definition.tier)
                    )
                    if crafting.tool_ceiling_for(definition.tier) else None
                ),
            }
            for definition, grade_id, count in await _ore_rows(db, character.id)
        ]
        tools = [
            {"ceiling": ceiling, "count": count}
            for ceiling, count in sorted((await craft_service.tools_of(db, character.id)).items())
        ]
        specs = _spec_payload(items[0]["source_id"]) if items else _spec_payload("surgeon_scalpel")

        return web.json_response({
            "items": items,
            "ore": ore,
            "tools": tools,
            "specs": specs,
            "efficiency": {
                "min": cc.EFFICIENCY_MIN,
                "craft_max": cc.EFFICIENCY_CRAFT_MAX,
                "max": cc.EFFICIENCY_MAX,
                "step": cc.EFFICIENCY_STEP,
            },
        })


async def _ore_rows(db, character_id: int):
    from services import mining_service

    return await mining_service.get_ore(db, character_id)


async def _body(request: web.Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def handle_post_craft(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    body = await _body(request)
    item_id, spec = body.get("item_id"), body.get("spec")
    ore_id, grade = body.get("ore_id"), body.get("grade")
    if not isinstance(item_id, int) or not isinstance(spec, str):
        return _error("bad_request")
    if not isinstance(ore_id, str) or not isinstance(grade, str):
        return _error("bad_request")

    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        try:
            result = await craft_service.craft(
                db, character, item_id, spec, ore_id, grade, _rng
            )
        except craft_service.CraftError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        return web.json_response({
            "item": _item_payload(character, result.item),
            "ore_spent": result.ore_spent,
            "was_recraft": result.was_recraft,
        })


async def handle_post_tool(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    body = await _body(request)
    ore_id, grade = body.get("ore_id"), body.get("grade")
    if not isinstance(ore_id, str) or not isinstance(grade, str):
        return _error("bad_request")

    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        try:
            ceiling = await craft_service.make_tool(db, character, ore_id, grade)
        except craft_service.CraftError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        return web.json_response({"ceiling": ceiling})


async def handle_post_upgrade(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    body = await _body(request)
    item_id, ceiling = body.get("item_id"), body.get("ceiling")
    if not isinstance(item_id, int) or not isinstance(ceiling, int):
        return _error("bad_request")

    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        try:
            result = await craft_service.upgrade(db, character, item_id, ceiling)
        except craft_service.CraftError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        return web.json_response({
            "item": _item_payload(character, result.item),
            "efficiency_before": result.efficiency_before,
            "efficiency_after": result.efficiency_after,
        })


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/craft", handle_get_craft)
    app.router.add_post("/api/miniapp/craft", handle_post_craft)
    app.router.add_post("/api/miniapp/craft/tool", handle_post_tool)
    app.router.add_post("/api/miniapp/craft/upgrade", handle_post_upgrade)
