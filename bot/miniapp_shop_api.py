"""Магазин мини-аппа: /api/miniapp/shop (2026-10-13).

GET - каталог с ценами на каждый срок и самоцветы игрока.
POST {"item": "premium", "days": N} - покупка; в ответ каталог заново и
итог покупки. Цена считается на сервере, личность - только из подписи.
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from services import onboarding_service as onboarding_svc
from services import shop_service, wallet_service


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        wallet = await wallet_service.get_wallet(db, character.id)
        await db.commit()
        return web.json_response(shop_service.catalog(character, wallet.donate_currency))


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict) or body.get("item") != shop_service.PREMIUM_ID:
        return _error("bad_request")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        # Вход игрока пишет свои строки - фиксируем отдельно, как на бирже.
        await db.commit()
        try:
            until = await shop_service.buy_premium(db, character, body.get("days"))
        except shop_service.ShopError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        wallet = await wallet_service.get_wallet(db, character.id)
        state = shop_service.catalog(character, wallet.donate_currency)
    state["done"] = {"item": shop_service.PREMIUM_ID, "days": body.get("days"), "until": until.isoformat()}
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/shop", handle_get)
    app.router.add_post("/api/miniapp/shop", handle_post)
