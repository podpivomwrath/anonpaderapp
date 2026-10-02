"""Эндпоинты биржи: /api/miniapp/exchange.

GET - курс, цены 1..10 лотов подряд, кошелёк, свои сделки, дневной график.
POST {"direction": "buy"|"sell", "lots": N} - сделка; в ответ то же, что GET.
Личность - только из request[VK_USER_ID_KEY].
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.combat import balance_config as bc
from services import exchange_service, wallet_service
from services import onboarding_service as onboarding_svc


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _order(order) -> dict:
    lots = order.amount // exchange_service.LOT
    return {
        "direction": order.direction, "lots": lots, "gems": order.amount, "gold": order.gold_amount,
        "per_lot": round(order.gold_amount / lots) if lots else order.gold_amount,
        "at": order.created_at.isoformat() if order.created_at else None,
    }


async def _state(db, character) -> dict:
    q = await exchange_service.quote(db)
    wallet = await wallet_service.get_wallet(db, character.id)
    return {
        "lot": exchange_service.LOT,
        "max_lots": exchange_service.MAX_LOTS,
        "buy_lot": q.buy_lot, "sell_lot": q.sell_lot,
        "buy_series": q.buy_series, "sell_series": q.sell_series,
        "start_lot": bc.EXCHANGE_START_LOT_PRICE,
        "growth_pct": round(bc.EXCHANGE_LOT_GROWTH * 100, 2),
        "spread_pct": round(bc.EXCHANGE_SPREAD_PCT * 100, 2),
        "gold": wallet.farm_currency, "gems": wallet.donate_currency,
        "mine": [_order(o) for o in await exchange_service.my_orders(db, character.id)],
        # График - по дням, обновляется раз в сутки (снимок после полуночи).
        # Курс уже взят под разделяемой блокировкой в quote(): повторный
        # FOR SHARE той же строки, пока в очереди ждёт сделка, Postgres
        # считает взаимной блокировкой - поэтому net передаём, а не перечитываем.
        "chart": await exchange_service.chart_points(db, net=q.net_sold),
    }


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()  # см. handle_post: вход игрока - своей транзакцией
        state = await _state(db, character)
        # quote() берёт строку курса под блокировкой - отпускаем сразу.
        await db.commit()
    return web.json_response(state)


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict):
        return _error("bad_request")
    direction, lots = body.get("direction"), body.get("lots")
    if direction not in ("buy", "sell"):
        return _error("bad_request")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        # Вход игрока (смена дня, гильдейские задания, last_active_at) пишет
        # свои строки - фиксируем его отдельно: сделка начинается без чужих
        # блокировок и первым делом берёт курс, а не ждёт его, держа что-то.
        await db.commit()
        try:
            if direction == "buy":
                order = await exchange_service.buy(db, character, lots)
            else:
                order = await exchange_service.sell(db, character, lots)
        except exchange_service.ExchangeError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        state = await _state(db, character)
        await db.commit()
    state["done"] = _order(order)
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/exchange", handle_get)
    app.router.add_post("/api/miniapp/exchange", handle_post)
