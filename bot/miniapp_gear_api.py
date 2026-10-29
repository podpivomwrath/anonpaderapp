"""Ремесленные инструменты в мини-аппе (2026-10-23): /api/miniapp/gear.

Страницы ремёсел на вкладке «Герой» (стрелка вправо): по ремеслу - уровень
и два слота. GET - что есть и что можно сделать дальше; POST {tool, tier} -
изготовить. Логика - services/craft_gear_service.py.
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import craft_gear
from game.economy import craft_gear_config as gc
from services import buffs_service, craft_gear_service
from services import onboarding_service as onboarding_svc

#: Инструменты, у которых ещё нет механики в игре: показываем «скоро», не даём
#: делать (не продаём то, что не работает).
NOT_READY: set[str] = set()

SOURCE_HINTS = {
    "almanac": "Добывается с мобов, очень редко.",
    "lamp": "Добывается в разломах.",
}


def _status(tool_id: str, row) -> str | None:
    """Альманах на зарядке (2026-10-29): работает или заряжается и сколько."""
    if tool_id != "almanac":
        return None
    from datetime import datetime, timezone

    total = craft_gear.almanac_uses(row.count)
    pages = f" Страниц: {row.count}." if row.count else ""
    left = craft_gear.almanac_charge_left(row.cycle_at, datetime.now(timezone.utc))
    if left:
        return f"Заряжается ещё {left} мин.{pages}"
    used = 0 if row.cycle_at is not None else (row.used or 0)
    return f"Подсказок до зарядки: {total - used} из {total}.{pages}"


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _next_step(db, character, tool: gc.ToolDef, row) -> dict | None:
    """Следующее изготовление: тир, нужный уровень, рецепт и что есть."""
    if tool.source == "drop" or tool.id in NOT_READY:
        return None
    stackable = tool.source in ("charges", "stock")
    level = getattr(character, gc.CRAFTS[tool.craft][2])
    if stackable:
        tier = 1
        if tool.source == "charges":
            # Самый высокий доступный тир, на который хватает трав; не хватает
            # ни на какой - показываем верхний, чтобы было видно, к чему идти.
            top = craft_gear.max_tier(tool, level)
            tier = top
            for t in range(top, 0, -1):
                if await craft_gear_service.herbs_have(db, character.id, t) >= tool.cost:
                    tier = t
                    break
    else:
        tier = (row.tier + 1) if row is not None else 1
        if tier > max(gc.TIERS):
            return None
    needs = craft_gear_service.recipe(tool, tier)
    ore_tier = 1 if tool.source == "stock" else tier
    have = {}
    if "ore" in needs:
        have["ore"] = await craft_gear_service.ore_have(db, character.id, ore_tier)
    if "herbs" in needs:
        have["herbs"] = await craft_gear_service.herbs_have(db, character.id, tier)
    if "fish_g" in needs:
        have["fish_g"] = await craft_gear_service.fish_have(db, character.id)
    need_level = craft_gear.level_for(tool, tier)
    can = level >= need_level and all(have.get(k, 0) >= v for k, v in needs.items())
    return {
        "tier": tier, "ore_tier": ore_tier, "need_level": need_level, "needs": needs, "have": have,
        "can": can, "effect": craft_gear.effect_line(tool.id, tier), "yield": tool.yield_ or None,
    }


async def _payload(db, character) -> dict:
    owned = await craft_gear_service.gear(db, character.id)
    crafts = []
    for craft_id, (emoji, title, level_field) in gc.CRAFTS.items():
        tools = []
        for tool in craft_gear.tools_of(craft_id):
            row = owned.get(tool.id)
            have = row is not None and (tool.source not in ("charges", "stock") or row.count > 0)
            tools.append({
                "id": tool.id, "slot": tool.slot, "title": tool.title, "emoji": tool.emoji,
                "source": tool.source, "owned": have,
                "tier": row.tier if have else 0, "count": row.count if row is not None else 0,
                "effect": craft_gear.effect_line(tool.id, row.tier) if have else None,
                "next": await _next_step(db, character, tool, row),
                "hint": SOURCE_HINTS.get(tool.id), "soon": tool.id in NOT_READY,
                # Что делает - видно и до находки (2026-10-23: у альманаха было
                # только «выпадает с мобов», а зачем он - нет).
                "about": craft_gear.effect_line(tool.id, 1) if tool.source == "drop" else None,
                "status": _status(tool.id, row) if have else None,
            })
        crafts.append({
            "id": craft_id, "emoji": emoji, "title": title,
            "level": getattr(character, level_field), "tools": tools,
        })
    # Действующие баффы - плашки слева от силуэта (2026-10-23).
    return {"crafts": crafts, "buffs": await buffs_service.active(db, character)}


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        return web.json_response(await _payload(db, character))


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    tool_id = body.get("tool") if isinstance(body, dict) else None
    tier = body.get("tier") if isinstance(body, dict) else None
    if not isinstance(tool_id, str) or not isinstance(tier, int) or tool_id in NOT_READY:
        return _error("bad_request")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        try:
            row = await craft_gear_service.make(db, character, tool_id, tier)
        except craft_gear_service.GearError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        done = {"tool": tool_id, "tier": row.tier, "count": row.count}
        await db.commit()
        payload = await _payload(db, character)
    payload["done"] = done
    return web.json_response(payload)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/gear", handle_get)
    app.router.add_post("/api/miniapp/gear", handle_post)
