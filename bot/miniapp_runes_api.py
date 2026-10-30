"""Руны в мини-аппе (2026-10-31): /api/miniapp/runes.

Страница «Руны» на вкладке «Герой»: три подвкладки (героя, экипировки,
навыков), все слоты сразу, закрытые - под замком с ценой. Руны героя ещё и
кругом под ногами силуэта. Логика - services/rune_service.py.
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import runes
from game.economy import runes_config as rc
from services import rune_service, wallet_service
from services import onboarding_service as onboarding_svc

PLACE_TITLES = {"weapon": "Оружие", "helmet": "Шлем", "armor": "Доспех", "legs": "Штаны", "boots": "Сапоги"}


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _rune(rune_def: rc.RuneDef, absorbed: int, count: int = 0) -> dict:
    nxt, nxt_pct = runes.next_threshold(rune_def.curve, absorbed)
    return {
        "id": rune_def.id, "kind": rune_def.kind, "name": rune_def.name, "rarity": rune_def.rarity,
        "rarity_title": rc.RARITY_TITLES[rune_def.rarity], "count": count,
        "text": runes.describe(rune_def, absorbed), "base_text": runes.describe(rune_def, 0),
        "pvp": rune_def.pvp, "ready": rune_def.ready,
        "classes": list(rune_def.classes), "place": rune_def.place,
        "tag": rc.SKILL_TAG_TITLES.get(rune_def.tag) if rune_def.tag else None, "tag_id": rune_def.tag or None,
        "absorbed": absorbed, "efficiency": round(runes.efficiency(rune_def.curve, absorbed) * 100, 1),
        "next": nxt, "next_pct": nxt_pct,
    }


async def _payload(db, character) -> dict:
    bag = await rune_service.bag(db, character.id)
    known = await rune_service.mastery(db, character.id)
    taken = {(r.kind, r.slot): r.rune_id for r in await rune_service.slots(db, character.id)}

    def socket(kind: str, slot: str, is_open: bool = True, price: int | None = None) -> dict:
        rune_id = taken.get((kind, slot))
        rune_def = rc.BY_ID.get(rune_id) if rune_id else None
        return {"slot": slot, "open": is_open, "price": price,
                "rune": _rune(rune_def, known.get(rune_id, 0)) if rune_def else None}

    hero = [
        socket(rc.HERO, str(i), i < character.rune_hero_slots,
               runes.hero_slot_price(i) if i == character.rune_hero_slots else None)
        for i in range(rc.HERO_SLOTS_MAX)
    ]
    gear = [
        {"place": place, "title": PLACE_TITLES[place],
         "slots": [socket(rc.GEAR, f"{place}:{i}") for i in range(rc.GEAR_SLOTS_PER_PLACE)]}
        for place in rc.GEAR_PLACES
    ]
    second = set(character.rune_skill_slots or [])
    skills = [
        {"id": s.id, "name": s.name, "tags": sorted(runes.skill_tags(s)),
         "slots": [socket(rc.SKILL, f"{s.id}:0"),
                   socket(rc.SKILL, f"{s.id}:1", s.id in second, None if s.id in second else rc.SKILL_SLOT_PRICE)]}
        for s in rune_service.skills_of(character)
    ]
    owned = [
        _rune(r, known.get(r.id, 0), bag.get(r.id, 0))
        for r in rc.RUNES if bag.get(r.id) or known.get(r.id) or any(v == r.id for v in taken.values())
    ]
    wallet = await wallet_service.get_wallet(db, character.id)
    return {
        "home": rune_service.at_home(character), "gold": wallet.farm_currency,
        "base_class": character.base_class,
        "hero": hero, "gear": gear, "skills": skills, "runes": owned,
        "titles": rc.KIND_TITLES, "skill_slot_price": rc.SKILL_SLOT_PRICE,
    }


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
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        return _error("bad_request")
    action = body["action"]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        try:
            if action == "equip":
                await rune_service.equip(db, character, str(body.get("kind")), str(body.get("slot")),
                                         str(body.get("rune")))
            elif action == "unequip":
                await rune_service.unequip(db, character, str(body.get("kind")), str(body.get("slot")))
            elif action == "absorb":
                count = body.get("count")
                if not isinstance(count, int) or count <= 0:
                    return _error("bad_request")
                await rune_service.absorb(db, character, str(body.get("rune")), count)
            elif action == "buy_hero":
                await rune_service.buy_hero_slot(db, character)
            elif action == "buy_skill":
                await rune_service.buy_skill_slot(db, character, str(body.get("skill")))
            else:
                return _error("bad_request")
        except rune_service.RuneError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        return web.json_response(await _payload(db, character))


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/runes", handle_get)
    app.router.add_post("/api/miniapp/runes", handle_post)
