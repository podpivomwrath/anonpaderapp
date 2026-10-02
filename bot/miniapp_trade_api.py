"""Эндпоинты торговли: /api/miniapp/trade.

GET - повозка, груз, Торговый дом или караван там, где стоишь, караваны на
карте. POST {"action": ..., ...} - сделка; в ответ то же, что GET, плюс
"done" - строка-итог для игрока. Личность - только из request[VK_USER_ID_KEY].
"""

import random
from datetime import datetime, timezone

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from bot.onboarding_texts import REGION_TITLES
from game.economy import mining
from game.economy import trade_config as tc
from game.world import grid
from game.world import world_config as wc
from models import CharacterOre
from services import mount_service, trade_service, wallet_service
from services import onboarding_service as onboarding_svc

_rng = random.Random()


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _good(good: tc.Good) -> dict:
    return {
        "id": good.id, "name": good.name, "emoji": good.emoji, "tier": good.tier,
        "tier_name": tc.TIER_NAMES[good.tier], "city": good.city, "city_title": REGION_TITLES[good.city],
    }


async def _ore_have(db, character_id: int, ore_id: str) -> int:
    from sqlalchemy import select

    return await db.scalar(
        select(CharacterOre.count).where(
            CharacterOre.character_id == character_id, CharacterOre.ore_id == ore_id, CharacterOre.grade == "common",
        )
    ) or 0


async def _state(db, character) -> dict:
    now = datetime.now(timezone.utc)
    wallet = await wallet_service.get_wallet(db, character.id)
    cart = await trade_service.get_cart(db, character.id)
    travel = await trade_service.cart_travel(db, character.id)
    cart_info = None
    if cart is not None:
        parts = []
        for part in tc.PARTS:
            level = getattr(cart, part.id)
            cost = trade_service.upgrade_cost(cart, part.id)
            parts.append({
                "id": part.id, "name": part.name, "emoji": part.emoji, "unit": part.unit,
                "level": level, "max": len(part.values), "value": part.values[level - 1],
                "next_value": part.values[level] if level < len(part.values) else None,
                "cost": None if cost is None else {
                    "gold": cost[0], "ore": mining.ore_def(cost[1]).name, "ore_count": cost[2],
                    "ore_have": await _ore_have(db, character.id, cost[1]),
                },
            })
        cargo = [
            {**_good(tc.GOODS_BY_ID[g]), "count": n, "paid": (cart.paid or {}).get(g, 0)}
            for g, n in (cart.cargo or {}).items()
        ]
        cart_info = {
            "x": cart.cart_x, "y": cart.cart_y,
            "here": (cart.cart_x, cart.cart_y) == (character.pos_x, character.pos_y) and travel is None,
            "traveling": travel is not None,
            "parts": parts, "durability": cart.durability, "max_durability": trade_service.max_durability(cart),
            "repair_cost": trade_service.repair_cost(cart),
            "cargo": cargo, "crates": trade_service.crates(cart), "capacity": trade_service.capacity(cart),
            "trade_level": cart.trade_level, "trade_xp": cart.trade_xp, "xp_next": tc.xp_to_next(cart.trade_level),
            "profit_total": cart.profit_total, "trip_ambush": trade_service.trip_ambush(cart),
            "step_seconds": trade_service.part_value(cart, "horses"),
        }
    place = await trade_service.place_here(db, character)
    place_info = None
    if place is not None:
        offers = await trade_service.offers(db, place, now)
        place_info = {
            "kind": place.kind, "title": place.title,
            "offers": [
                {
                    **_good(o.good), "buy": o.buy, "sell": o.sell, "stock": o.stock,
                    "locked": cart is not None and cart.trade_level < tc.TIER_MIN_TRADE_LEVEL[o.good.tier],
                    "min_level": tc.TIER_MIN_TRADE_LEVEL[o.good.tier],
                    "deficit": place.kind == "city" and o.good.city in tc.DEFICIT[place.city],
                }
                for o in offers if o.buy is not None or o.sell is not None
            ],
        }
    caravans = []
    for c in await trade_service.active_caravans(db, now):
        expires = c.expires_at if c.expires_at.tzinfo else c.expires_at.replace(tzinfo=timezone.utc)
        caravans.append({
            "id": c.id, "x": c.x, "y": c.y,
            "minutes_left": max(int((expires - now).total_seconds() // 60), 0),
            "buys": [{**_good(tc.GOODS_BY_ID[g]), "left": n, "price": trade_service.caravan_sell_price(tc.GOODS_BY_ID[g])} for g, n in c.buys.items()],
            "sells": [{**_good(tc.GOODS_BY_ID[g]), "left": n, "price": trade_service.caravan_buy_price(tc.GOODS_BY_ID[g])} for g, n in c.sells.items()],
        })
    return {
        "level": character.level, "min_level": tc.TRADE_MIN_LEVEL, "cart_price": tc.CART_PRICE,
        "gold": wallet.farm_currency, "pos": [character.pos_x, character.pos_y],
        "cart": cart_info, "place": place_info, "caravans": caravans,
        "cities": [
            {
                "region": r, "title": REGION_TITLES[r], "x": x, "y": y,
                # Чьи товары здесь в дефиците - готовой строкой.
                "wants": ", ".join(REGION_TITLES[d] for d in sorted(tc.DEFICIT[r])),
            }
            for r, (x, y) in wc.CITY_COORDS.items()
        ],
    }


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()
        state = await _state(db, character)
        await db.commit()
    return web.json_response(state)


def _deal_text(deal, selling: bool) -> str:
    g = deal.good
    if not selling:
        return f"Куплено: {g.emoji} {g.name} ×{deal.count} за {deal.gold} золота."
    text = f"Продано: {g.emoji} {g.name} ×{deal.count} за {deal.gold} золота (прибыль {deal.profit:+d})."
    if deal.level_up:
        text += f" Уровень торговли: {deal.level_up}!"
    if deal.chests:
        text += f" 🎁 В ящиках нашёлся Пепельный ларец ×{deal.chests}!"
    return text


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        return _error("bad_request")
    action = body["action"]
    travel_started = None
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()  # вход игрока - своей транзакцией, как на бирже
        try:
            if action == "buy_cart":
                await trade_service.buy_cart(db, character)
                done = "🐂 Повозка куплена. Грузи товар и в путь."
            elif action == "buy":
                done = _deal_text(await trade_service.buy(db, character, body.get("good"), body.get("count")), False)
            elif action == "sell":
                done = _deal_text(await trade_service.sell(db, character, body.get("good"), body.get("count"), _rng), True)
            elif action == "upgrade":
                cart = await trade_service.upgrade(db, character, body.get("part"))
                part = tc.PARTS_BY_ID[body["part"]]
                done = f"{part.emoji} {part.name}: уровень {getattr(cart, part.id)}."
            elif action == "repair":
                done = f"🛠 Обшивка починена за {await trade_service.repair(db, character)} золота."
            elif action == "send":
                travel = await trade_service.send(db, character, body.get("x"), body.get("y"))
                travel_started = travel
                done = f"🐂 Повозка тронулась к ({travel.to_x}; {travel.to_y})."
            else:
                return _error("bad_request")
        except trade_service.TradeError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        if travel_started is not None:
            seconds = mount_service.remaining_seconds(travel_started)
            cart = await trade_service.get_cart(db, character.id)
            chance = mount_service.trip_ambush_chance(
                tc.CART_MOUNT_ID, character.pos_x, character.pos_y, travel_started.to_x, travel_started.to_y,
                trade_service.trip_ambush(cart),
            )
        await db.commit()
        if travel_started is not None:
            from bot.handlers import mounts as mounts_handlers  # избегаем цикла импортов

            await mounts_handlers.notify_travel_started(
                request[VK_USER_ID_KEY], travel_started.to_x, travel_started.to_y, seconds, chance, icon="🐂",
            )
        state = await _state(db, character)
        await db.commit()
    state["done"] = done
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/trade", handle_get)
    app.router.add_post("/api/miniapp/trade", handle_post)
