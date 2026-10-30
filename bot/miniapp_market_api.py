"""Рынок в мини-аппе (2026-10-23): /api/miniapp/market.

GET - каталог с лучшими ценами, свои товары, свои заявки, ящик купленного,
витрина и свои вещи для неё. GET ?good=<ключ> - стакан и история цен товара.
POST {action: sell|buy|list_item|buy_item|cancel|claim|courier, ...} - действие; в ответ
то же, что GET, плюс done. Логика - services/market_service.py.
"""

from aiohttp import web

from bot import market_notice
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import market_config as mc
from game.world import grid
from models import Item
from services import courier_service, item_service, market_service, naming, rune_service, wallet_service
from services import onboarding_service as onboarding_svc


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _good(g) -> dict:
    return {"key": g.key, "category": g.category, "name": g.name, "emoji": g.emoji, "icon": g.icon,
            "base": g.base or g.name, "variant": g.variant}


def _about(key: str) -> dict:
    """Страничка товара (2026-10-24, владелец: «для еды - посмотреть бафф»):
    описание и что даёт - те же тексты, что в инвентаре."""
    from game.economy import cooking, craft_gear, herbalism, mining
    from game.economy import cooking_config as cc
    from services import lootbox_service

    kind, _, rest = key.partition(":")
    if kind == "ore":
        ore = mining.ore_def(rest.split(":")[0])
        return {"description": ore.description if ore else None, "effect": None}
    if kind == "herb":
        herb = herbalism.herb_def(rest)
        return {"description": herb.description if herb else None, "effect": None}
    if kind == "food":
        dish_id, _, grade = rest.partition(":")
        dish, d = cc.DISHES_BY_ID.get(dish_id), cooking.dish_def(dish_id)
        if dish is None or d is None:
            return {"description": None, "effect": None}
        return {"description": d.description, "effect": cooking.buff_text(dish, grade)}
    if kind == "craft":
        return {"description": None, "effect": craft_gear.effect_line(rest, 1) or None}
    if kind == "rune":
        return rune_about(rest)
    if kind == "chest":
        info = lootbox_service.CHEST_KINDS.get(rest)
        return {"description": info.description if info else None, "effect": None}
    return {"description": None, "effect": None}


def rune_about(rune_id: str, absorbed: int = 0) -> dict:
    """Сводка руны на рынке (2026-10-31, владелец): вид, для кого, что даёт,
    как растёт и как в PvP."""
    from game.economy import runes
    from game.economy import runes_config as rc

    r = rc.BY_ID.get(rune_id)
    if r is None:
        return {"description": None, "effect": None}
    lines = [f"{rc.KIND_ONE[r.kind]}, {rc.RARITY_TITLES[r.rarity]}."]
    classes = {"warrior": "воина", "rogue": "разбойника", "mage": "мага"}
    if r.kind == rc.GEAR:
        who = ", ".join(classes[c] for c in r.classes) if r.classes else "любого класса"
        lines.append(f"Вставляется в {'оружие' if r.place == 'weapon' else 'доспех'}, для {who}.")
    if r.kind == rc.SKILL:
        lines.append(f"Вставляется в {rc.SKILL_TAG_TITLES[r.tag] if r.tag else 'любой навык'}.")
    first, second = runes.threshold(r.curve, 1), runes.threshold(r.curve, 2)
    lines.append(f"Мастерство: 110% - {first} копий, 120% - {second}.")
    lines.append({"full": "В PvP в полную силу.", "half": "В PvP вполсилы.",
                  "none": "В PvP не действует."}[r.pvp])
    if not r.ready:
        lines.append("Пока не действует - подключим в ближайших обновлениях.")
    effect = "При 100%: " + runes.describe(r, 0)
    if absorbed:
        effect += f". У тебя {runes.efficiency(r.curve, absorbed) * 100:.0f}%: " + runes.describe(r, absorbed)
    return {"description": " ".join(lines), "effect": effect + "."}


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
        # Курьер (2026-10-24): есть ли он и свободен ли - для кнопки «Принести курьером».
        "courier": bool(character.has_courier),
        "courier_busy": await courier_service.active_of(db, character.id) is not None,
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
                "about": rune_about(key[5:], (await rune_service.mastery(db, character.id)).get(key[5:], 0))
                if key.startswith("rune:") else _about(key),
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
            elif action == "courier":
                done["lines"] = await market_service.send_courier(db, character)
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
