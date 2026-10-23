"""Рынок в мини-аппе (2026-10-23): /api/miniapp/market.

GET - каталог с лучшими ценами, свои товары, свои заявки, ящик купленного,
витрина и свои вещи для неё. GET ?good=<ключ> - стакан и история цен товара.
POST {action: sell|buy|list_item|buy_item|cancel|claim, ...} - действие; в ответ
то же, что GET, плюс done. Логика - services/market_service.py.
"""

from aiohttp import web

from bot import market_notice
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import market_config as mc
from game.world import grid
from models import Item
from services import item_service, market_service, naming, wallet_service
from services import onboarding_service as onboarding_svc


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _good(g) -> dict:
    return {"key": g.key, "category": g.category, "name": g.name, "emoji": g.emoji, "icon": g.icon,
            "base": g.base or g.name, "variant": g.variant}


async def _order(db, o) -> dict:
    return {
        "id": o.id, "side": o.side, "good": o.good, "name": await market_service.label(db, o.good),
        "price": o.price, "qty_total": o.qty_total, "qty_left": o.qty_left,
        "expires_at": o.expires_at.isoformat() if o.expires_at else None,
    }


def _item(item) -> dict:
    return {
        "id": item.id, "name": item.name, "slot": item.slot, "rarity": item.rarity,
        "icon": naming.item_icon_key(item),
        "stats": dict(item.base_stats or {}), "power": item_service.item_power(item),
        "label": item_service.format_item_label(item),
    }


async def _state(db, character) -> dict:
    wallet = await wallet_service.get_wallet(db, character.id)
    summary = await market_service.summary(db)
    showcase = []
    for o in await market_service.showcase(db):
        item = await db.get(Item, int(o.good.split(":", 1)[1]))
        if item is not None:
            showcase.append({**await _order(db, o), "item": _item(item), "mine": o.character_id == character.id})
    trades = []
    for t in await market_service.my_trades(db, character.id):
        trades.append({
            "good": t.good, "name": await market_service.label(db, t.good), "price": t.price, "qty": t.qty,
            "side": "buy" if t.buyer_id == character.id else "sell",
            "at": t.created_at.isoformat() if t.created_at else None,
        })
    return {
        "gold": wallet.farm_currency,
        "categories": [{"id": c, "title": t} for c, t in mc.CATEGORIES],
        "goods": [{**_good(g), **summary.get(g.key, {})} for g in mc.goods().values()],
        "have": await market_service.holdings(db, character.id),
        "orders": [await _order(db, o) for o in await market_service.my_orders(db, character.id)],
        "inbox": [{"good": r.good, "name": await market_service.label(db, r.good), "qty": r.qty}
                  for r in await market_service.inbox(db, character.id)],
        "in_city": grid.city_region_at(character.pos_x, character.pos_y) is not None,
        "showcase": showcase,
        "my_items": [_item(i) for i in await market_service.sellable_items(db, character.id)],
        "trades": trades,
        "rules": {
            "listing_fee_pct": round(mc.LISTING_FEE * 100, 2), "sale_fee_pct": round(mc.SALE_FEE * 100, 2),
            "min_gold": mc.MIN_ORDER_GOLD, "hours": mc.ORDER_HOURS,
            "max_orders": market_service.limit_for(character),
        },
    }


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()
        key = request.query.get("good")
        if key:
            if mc.good(key) is None:
                return _error("bad_request")
            return web.json_response({
                "book": await market_service.book(db, key),
                "history": await market_service.history(db, key),
                "have": (await market_service.holdings(db, character.id)).get(key, 0),
            })
        return web.json_response(await _state(db, character))


def _int(body: dict, name: str) -> int:
    value = body.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise market_service.MarketError("bad_request")
    return value


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict):
        return _error("bad_request")
    action = body.get("action")
    notices = []
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()
        try:
            done: dict = {"action": action}
            if action in ("sell", "buy"):
                key = body.get("good")
                if not isinstance(key, str):
                    raise market_service.MarketError("bad_request")
                place = market_service.place_sell if action == "sell" else market_service.place_buy
                res = await place(db, character, key, _int(body, "qty"), _int(body, "price"))
                notices, done["filled"], done["gold"] = res.notices, res.filled, res.gold
            elif action == "list_item":
                await market_service.list_item(db, character, _int(body, "item_id"), _int(body, "price"))
            elif action == "buy_item":
                res = await market_service.buy_item(db, character, _int(body, "order_id"))
                notices = res.notices
            elif action == "cancel":
                await market_service.cancel(db, character, _int(body, "order_id"))
            elif action == "claim":
                done["lines"] = await market_service.claim(db, character)
            else:
                return _error("bad_request")
            await db.commit()
        except market_service.MarketError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        state = await _state(db, character)
    market_notice.tell(notices)
    state["done"] = done
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/market", handle_get)
    app.router.add_post("/api/miniapp/market", handle_post)
