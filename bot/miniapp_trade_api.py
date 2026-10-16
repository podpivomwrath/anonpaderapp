"""Эндпоинты вкладки «Фракция»: торговая фирма и процветание городов.

GET /api/miniapp/trade - фирма, повозки, цены городов, процветание, журнал.
POST {"action": ..., ...} - действие; в ответ то же, что GET, плюс "done" -
строка-итог для игрока. Личность - только из request[VK_USER_ID_KEY].
"""

import random
from datetime import datetime, timezone

from aiohttp import web
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from bot.onboarding_texts import REGION_TITLES
from game.economy import faction_config as fc
from game.economy import mining
from game.economy import trade_config as tc
from models import Character, CharacterOre, TradeContribution, TradeFirm
from services import faction_service, trade_service, wallet_service
from services import onboarding_service as onboarding_svc

_rng = random.Random()


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _good(good: tc.Good) -> dict:
    return {
        "id": good.id, "name": good.name, "emoji": good.emoji, "tier": good.tier,
        "tier_name": tc.TIER_NAMES[good.tier], "city": good.city, "city_title": REGION_TITLES[good.city],
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _ore_have(db, character_id: int) -> dict[str, int]:
    rows = (await db.execute(
        select(CharacterOre.ore_id, CharacterOre.count).where(
            CharacterOre.character_id == character_id, CharacterOre.grade == "common",
        )
    )).all()
    return dict(rows)


def _tier(t: fc.Tier) -> dict:
    return {
        "id": t.id, "name": t.name, "emoji": t.emoji, "min_points": t.min_points,
        "elixir_pct": round((t.elixir_mult - 1) * 100), "relic_pct": round((t.relic_mult - 1) * 100),
    }


async def _factions(db, now: datetime) -> list[dict]:
    points = await faction_service.points(db, now)
    today = faction_service.msk_day(now)
    brought = dict((await db.execute(
        select(TradeContribution.city, func.coalesce(func.sum(TradeContribution.points), 0))
        .where(TradeContribution.day == today).group_by(TradeContribution.city)
    )).all())
    week = faction_service.week_start(today)
    out = []
    for city in fc.CITIES:
        p = points[city]
        nxt = fc.next_tier(p)
        first_id = await faction_service.first_supplier(db, city, now)
        first = await db.get(Character, first_id) if first_id else None
        out.append({
            "first_supplier": first.name if first is not None else None,
            "week_top": [{"name": n, "points": raw} for _, n, raw in await faction_service.week_top(db, city, week)],
            "city": city, "title": REGION_TITLES[city], "points": round(p), "max": fc.MAX_POINTS,
            "tier": _tier(fc.tier_for(p)),
            "next": {"name": nxt.name, "emoji": nxt.emoji, "min_points": nxt.min_points} if nxt else None,
            "today": int(brought.get(city, 0)),
            "decay_day": round(p * fc.DECAY_PER_DAY),
        })
    return out


def _order(order, level: int, now: datetime) -> dict:
    return {
        "id": order.id, "city": order.city, "title": REGION_TITLES[order.city],
        "good": _good(tc.GOODS_BY_ID[order.good_id]), "total": order.total, "left": order.left,
        "price": trade_service.order_price(order, level),
        "minutes_left": max(int((_aware(order.expires_at) - now).total_seconds() // 60), 0),
    }


def _cart(cart, level: int, ore_have: dict, prices: dict, now: datetime) -> dict:
    parts = []
    for part in tc.PARTS:
        lvl = getattr(cart, part.id)
        cost = trade_service.upgrade_cost(cart, part.id)
        parts.append({
            "id": part.id, "name": part.name, "emoji": part.emoji, "unit": part.unit,
            "level": lvl, "max": len(part.values), "value": trade_service.part_value(cart, part.id),
            "next_value": part.values[lvl] if lvl < len(part.values) else None,
            "cost": None if cost is None else {
                "gold": cost[0], "ore": mining.ore_def(cost[1]).name, "ore_count": cost[2],
                "ore_have": ore_have.get(cost[1], 0),
            },
        })
    info = {
        "slot": cart.slot, "city": cart.city, "city_title": REGION_TITLES[cart.city],
        "status": cart.status, "parts": parts,
        "capacity": trade_service.capacity(cart), "crates": trade_service.crates(cart),
        "cargo": [{**_good(tc.GOODS_BY_ID[g]), "count": n} for g, n in (cart.cargo or {}).items()],
        "durability": cart.durability, "max_durability": trade_service.max_durability(cart),
        "repair_cost": trade_service.repair_cost(cart),
    }
    if cart.status == "traveling":
        info.update({
            "to_city": cart.to_city, "to_title": REGION_TITLES[cart.to_city], "route": cart.route,
            "seconds_left": max(int((_aware(cart.arrives_at) - now).total_seconds()), 0),
        })
        return info
    # Что можно закупить здесь и куда везти: пути и шанс нападения.
    info["goods"] = [
        {
            **_good(g), "price": trade_service.city_buy_price(cart.city, g, prices.get((cart.city, g.id), 0.0)),
            "locked": level < tc.TIER_MIN_TRADE_LEVEL[g.tier], "min_level": tc.TIER_MIN_TRADE_LEVEL[g.tier],
        }
        for g in tc.GOODS if g.city == cart.city
    ]
    destinations = []
    for city in fc.CITIES:
        if city == cart.city:
            continue
        routes = {}
        for route in tc.ROUTES:
            cells = trade_service.path(cart.city, city, route)
            routes[route] = {
                "cells": len(cells), "seconds": round(trade_service.trip_seconds(cart, len(cells), route)),
                "ambush": round(trade_service.ambush_chance(cart, cells), 3),
            }
        destinations.append({
            "city": city, "title": REGION_TITLES[city], "routes": routes,
            "kind": "deficit" if city in tc.DEFICIT[cart.city] else "far",
            # Цена за ящик каждого товара этого города там (с бонусом уровня).
            "prices": {
                g.id: tc.with_sell_bonus(
                    trade_service.city_sell_price(city, g, prices.get((city, g.id), 0.0)), level,
                )
                for g in tc.GOODS if g.city == cart.city
            },
        })
    info["destinations"] = destinations
    return info


async def _state(db, character) -> dict:
    now = datetime.now(timezone.utc)
    wallet = await wallet_service.get_wallet(db, character.id)
    firm = await trade_service.get_firm(db, character.id)
    state = {
        "level": character.level, "min_level": tc.TRADE_MIN_LEVEL, "firm_price": tc.FIRM_PRICE,
        "gold": wallet.farm_currency, "home": character.region,
        "home_title": REGION_TITLES.get(character.region or "", ""),
        "name_min": tc.FIRM_NAME_MIN, "name_max": tc.FIRM_NAME_MAX,
        "firm": None, "carts": [], "trips": [],
        "factions": await _factions(db, now),
        "tiers": [_tier(t) for t in fc.TIERS],
        "routes": {r: tc.ROUTE_TITLES[r] for r in tc.ROUTES},
        "orders": [],
        "order_bonus_pct": round((tc.ORDER_PRICE_MULT - 1) * 100),
    }
    level = firm.trade_level if firm is not None else 1
    state["orders"] = [_order(o, level, now) for o in await trade_service.active_orders(db, now)]
    if firm is None:
        return state
    carts = await trade_service.carts(db, character.id)
    nxt = trade_service.next_slot_need(len(carts))
    state["firm"] = {
        "name": firm.name, "trade_level": firm.trade_level,
        # Перенесена со старой повозки (ещё без названия, но с историей).
        "migrated": firm.name is None and (firm.trade_level > 1 or firm.profit_total > 0 or firm.trade_xp > 0), "trade_xp": firm.trade_xp,
        "xp_next": tc.xp_to_next(firm.trade_level),
        "sell_bonus_pct": round(tc.sell_bonus(firm.trade_level) * 100),
        "profit_total": firm.profit_total,
        "notify_arrival": firm.notify_arrival, "notify_orders": firm.notify_orders,
        "today_points": await faction_service.today_points(db, character.id, now),
        "daily_cap": fc.daily_cap(firm.trade_level),
        "next_cart": {"slot": len(carts) + 1, "level": nxt[0], "gold": nxt[1]} if nxt else None,
    }
    prices = await trade_service.pressures(db, now)
    ore_have = await _ore_have(db, character.id)
    state["carts"] = [_cart(c, firm.trade_level, ore_have, prices, now) for c in carts]
    state["trips"] = [
        {
            "id": t.id, "slot": t.slot, "from_title": REGION_TITLES[t.from_city], "to_title": REGION_TITLES[t.to_city],
            "route": t.route, "crates": t.crates, "revenue": t.revenue, "profit": t.profit,
            "ambushes": t.ambushes, "lost": trade_service.lost_text(t.lost or {}),
            "event": tc.TRIP_EVENTS_BY_ID[t.event].text if t.event in tc.TRIP_EVENTS_BY_ID else None,
            "order_crates": t.order_crates,
            "minutes_ago": max(int((now - _aware(t.arrived_at)).total_seconds() // 60), 0),
        }
        for t in await trade_service.recent_trips(db, character.id)
    ]
    return state


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        state = await _state(db, character)
        await db.commit()
    return web.json_response(state)


def _minutes(seconds: float) -> str:
    return f"{max(round(seconds / 60), 1)} мин"


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
        await db.commit()  # вход игрока - своей транзакцией, как на бирже
        try:
            if action == "buy_firm":
                await trade_service.buy_firm(db, character)
                done = "🏛 Торговая фирма открыта, первая повозка ждёт в родном городе. Осталось дать фирме название."
            elif action == "name_firm":
                firm = await trade_service.name_firm(db, character, body.get("name"))
                done = f"🏛 Фирма теперь называется «{firm.name}»."
            elif action == "buy_cart":
                cart = await trade_service.buy_cart(db, character)
                done = f"🐂 Повозка №{cart.slot} куплена и ждёт в {REGION_TITLES[cart.city]}."
            elif action == "upgrade":
                cart = await trade_service.upgrade(db, character, body.get("slot"), body.get("part"))
                part = tc.PARTS_BY_ID[body["part"]]
                done = f"{part.emoji} Повозка №{cart.slot}: {part.name.lower()} - уровень {getattr(cart, part.id)}."
            elif action == "repair":
                cost = await trade_service.repair(db, character, body.get("slot"))
                done = f"🛠 Обшивка починена за {cost} золота."
            elif action == "dispatch":
                sent = await trade_service.dispatch(
                    db, character, body.get("slot"), body.get("to"), body.get("route"), body.get("goods") or {}, _rng,
                )
                cart = sent.cart
                what = f"{sent.crates} ящ. за {sent.cost} золота" if sent.crates else "порожняком"
                done = (
                    f"🐂 Повозка №{cart.slot} ушла в {REGION_TITLES[cart.to_city]} ({what}), "
                    f"в пути ~{_minutes(sent.seconds)}."
                )
            elif action == "notify":
                await trade_service.set_notify(db, character, body.get("arrival"), body.get("orders"))
                done = "Настройки сохранены."
            else:
                return _error("bad_request")
            await db.commit()
        except trade_service.TradeError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        except IntegrityError:
            # Название заняли в ту же секунду - уникальность держит база.
            await db.rollback()
            return _error("Фирма с таким названием уже есть.", 409)
        state = await _state(db, character)
        await db.commit()
    state["done"] = done
    return web.json_response(state)


#: Сколько торговцев показывать в сводке города.
CITY_TOP = 10


async def city_summary(db, city: str, now: datetime | None = None) -> dict:
    """Сводка города (2026-10-16, клик по городу во вкладке «Фракция»): что он
    производит и почём, что скупает и почём, лучшие торговцы города за всё
    время (очки процветания без дневного потолка) и за эту неделю."""
    now = now or datetime.now(timezone.utc)
    prices = await trade_service.pressures(db, now)
    makes = [
        {**_good(g), "price": trade_service.city_buy_price(city, g, prices.get((city, g.id), 0.0))}
        for g in tc.GOODS if g.city == city
    ]
    buys = [
        {
            **_good(g), "price": trade_service.city_sell_price(city, g, prices.get((city, g.id), 0.0)),
            "deficit": city in tc.DEFICIT[g.city],
        }
        for g in tc.GOODS if g.city != city
    ]
    buys.sort(key=lambda g: (-g["price"], g["tier"]))
    week = faction_service.week_start(faction_service.msk_day(now))
    total = func.sum(TradeContribution.raw)
    week_points = func.sum(case((TradeContribution.day >= week, TradeContribution.raw), else_=0))
    # Засчитано городу - с дневным потолком; рейтинг - по сданному без него.
    credited = func.sum(TradeContribution.points)
    rows = (await db.execute(
        select(Character.name, TradeFirm.name, TradeFirm.trade_level, total, week_points, credited)
        .join(Character, Character.id == TradeContribution.character_id)
        .outerjoin(TradeFirm, TradeFirm.character_id == TradeContribution.character_id)
        .where(TradeContribution.city == city)
        .group_by(TradeContribution.character_id, Character.name, TradeFirm.name, TradeFirm.trade_level)
        .having(total > 0)
        .order_by(total.desc(), TradeContribution.character_id)
        .limit(CITY_TOP)
    )).all()
    traders = await db.scalar(
        select(func.count(TradeFirm.character_id)).join(Character, Character.id == TradeFirm.character_id)
        .where(Character.region == city)
    )
    return {
        "city": city, "title": REGION_TITLES[city], "makes": makes, "buys": buys, "firms": int(traders or 0),
        "top": [
            {
                "name": name, "firm": firm, "trade_level": lvl, "points": int(pts), "week": int(wk or 0),
                "credited": int(cr or 0),
            }
            for name, firm, lvl, pts, wk, cr in rows
        ],
    }


async def handle_city(request: web.Request) -> web.Response:
    city = request.query.get("city", "")
    if city not in fc.CITIES:
        return _error("bad_request")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        if await onboarding_svc.get_character(db, request[VK_USER_ID_KEY]) is None:
            return _error("character_not_found", 404)
        summary = await city_summary(db, city)
        await db.commit()
    return web.json_response(summary)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/trade/city", handle_city)
    app.router.add_get("/api/miniapp/trade", handle_get)
    app.router.add_post("/api/miniapp/trade", handle_post)
