"""Магазин мини-аппа: /api/miniapp/shop (2026-10-13).

GET - каталог с ценами на каждый срок и самоцветы игрока.
POST {"item": "premium", "days": N} - покупка; в ответ каталог заново и
итог покупки. Цена считается на сервере, личность - только из подписи.
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from services import onboarding_service as onboarding_svc
from bot.onboarding_texts import REGION_TITLES
from services import shop_service, wallet_service


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _catalog(db, character) -> dict:
    from services import trade_service

    wallet = await wallet_service.get_wallet(db, character.id)
    firm = await trade_service.get_firm(db, character.id)
    return shop_service.catalog(character, wallet.donate_currency, firm.name if firm is not None else None)


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        state = await _catalog(db, character)
        await db.commit()
        return web.json_response(state)


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    item = body.get("item") if isinstance(body, dict) else None
    if item not in (shop_service.PREMIUM_ID, shop_service.RENAME_ID, shop_service.FIRM_RENAME_ID,
                    shop_service.ELIXIR_PACK_ID, shop_service.TINCTURE_ID, shop_service.POCKET_ID,
                    shop_service.FACTION_ID, shop_service.COURIER_ID):
        return _error("bad_request")
    peer_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        # Вход игрока пишет свои строки - фиксируем отдельно, как на бирже.
        await db.commit()
        from sqlalchemy.exc import IntegrityError

        # Смена фракции в бою (и в разломе, событии) не отказывает: оплачена
        # сейчас, переезд - после боя (move_pending_job).
        busy = item == shop_service.FACTION_ID and await faction_blocker(peer_id, character) is not None
        moved = None

        try:
            if item == shop_service.PREMIUM_ID:
                until = await shop_service.buy_premium(db, character, body.get("days"))
                done = {"item": item, "days": body.get("days"), "until": until.isoformat()}
            elif item == shop_service.ELIXIR_PACK_ID:
                done = {"item": item, "contents": await shop_service.buy_elixir_pack(db, character)}
            elif item == shop_service.TINCTURE_ID:
                until = await shop_service.buy_tincture(db, character)
                done = {"item": item, "until": until.isoformat()}
            elif item == shop_service.POCKET_ID:
                await shop_service.buy_pocket(db, character)
                done = {"item": item}
            elif item == shop_service.COURIER_ID:
                await shop_service.buy_courier(db, character)
                done = {"item": item}
            elif item == shop_service.FACTION_ID:
                region = body.get("region")
                voyage_text = await shop_service.change_faction(db, character, region, defer=busy)
                pending = character.pending_faction is not None
                done = {"item": item, "region": region, "title": REGION_TITLES[region], "pending": pending}
                if not pending:
                    moved = (region, voyage_text)
            elif item == shop_service.RENAME_ID:
                old = await shop_service.rename_character(db, character, body.get("name"))
                done = {"item": item, "old": old, "name": character.name}
            else:
                old = await shop_service.rename_firm(db, character, body.get("name"))
                done = {"item": item, "old": old}
            await db.commit()
        except shop_service.ShopError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        except IntegrityError:
            # Имя заняли в ту же секунду - уникальность держит база.
            await db.rollback()
            return _error("Это имя только что заняли - выбери другое.", 409)
        state = await _catalog(db, character)
        await db.commit()
    if item == shop_service.FIRM_RENAME_ID:
        done["name"] = next(i for i in state["items"] if i["id"] == item)["current"]
    if moved is not None:
        await after_faction_move(peer_id, *moved)
    state["done"] = done
    return web.json_response(state)


async def faction_blocker(peer_id: int, character) -> str | None:
    """Переезд нельзя посреди того, что живёт в памяти бота: боя, рейда,
    разлома, события. Остальное change_faction заканчивает сам."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import raid_combat, rift, scene_events

    if in_any_battle(peer_id) or raid_combat.has_active_raid(character.id):
        return "Сначала закончи бой."
    if rift.is_waiting(peer_id):
        return "Ты ждёшь разлом - сначала выйди из очереди."
    if scene_events.has_pending(peer_id):
        return "Сначала закончи событие."
    return None


async def move_pending_job() -> None:
    """Раз в несколько секунд: переезды, оплаченные в бою, - тем, у кого бой
    кончился и кто жив."""
    from sqlalchemy import select

    from models import Character, User
    from services import death_service
    from services.db import get_session_factory

    async with get_session_factory()() as db:
        rows = (await db.execute(
            select(Character.id, User.vk_id).join(User, User.id == Character.user_id)
            .where(Character.pending_faction.isnot(None))
        )).all()
        await db.rollback()
    for character_id, peer_id in rows:
        try:
            async with get_session_factory()() as db:
                character = await db.get(Character, character_id, with_for_update=True)
                if (character is None or character.pending_faction is None
                        or death_service.is_dead(character)
                        or await faction_blocker(peer_id, character) is not None):
                    await db.rollback()
                    continue
                region = character.pending_faction
                voyage_text = await shop_service.move_pending(db, character)
                await db.commit()
            await after_faction_move(peer_id, region, voyage_text)
        except Exception:
            from loguru import logger

            logger.exception("Смена фракции после боя не прошла: персонаж {}", character_id)


async def after_faction_move(peer_id: int, region: str, voyage_text: str | None) -> None:
    """Снять то, что живёт в памяти бота, и показать площадь нового города."""
    from bot.handlers import mounts, voyage, world
    from bot import pending_activity

    world._exploring.discard(peer_id)
    world._resting.discard(peer_id)
    await pending_activity.forget("explore", peer_id)
    await pending_activity.forget("rest", peer_id)
    voyage._away.discard(peer_id)
    header = FACTION_MOVE_TEXT.format(city=REGION_TITLES[region])
    if voyage_text:
        header = f"{voyage_text}\n\n{header}"
    try:
        await mounts.send_cell_screen(peer_id, header)
    except Exception:
        from loguru import logger

        logger.exception("Смена фракции: не удалось показать город {}", peer_id)


FACTION_MOVE_TEXT = (
    "🏳 Писарь у ворот вписывает тебя в книгу жителей, даже не подняв головы. "
    "Новый дом - {city}."
)


# --- Самоцветы за рубли (ЮKassa, 2026-10-15) ---------------------------------


async def handle_get_payments(request: web.Request) -> web.Response:
    from bot.app_keys import SETTINGS_KEY
    from services import payment_service

    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        rows = await payment_service.history(db, character.id)
        await db.commit()
    return web.json_response({
        "enabled": payment_service.enabled(request.app[SETTINGS_KEY]),
        "packs": payment_service.packs_payload(),
        "history": [
            {"pack_id": r.pack_id, "gems": r.gems, "rub": r.amount_rub, "status": r.status,
             "credited": r.credited, "at": (r.paid_at or r.created_at).isoformat()}
            for r in rows
        ],
    })


async def handle_post_payment(request: web.Request) -> web.Response:
    """{"pack_id": ..., "from": "vk" | "web"} -> {"url": ссылка на оплату}."""
    from bot.app_keys import SETTINGS_KEY
    from services import payment_service

    settings = request.app[SETTINGS_KEY]
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict):
        return _error("bad_request")
    vk_id = request[VK_USER_ID_KEY]
    if body.get("from") == "web":
        return_url = f"{settings.site_url.rstrip('/')}/?paid=1"
    else:
        return_url = settings.vk_miniapp_url or "https://vk.com/app54687822"
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_id)
        if character is None:
            return _error("character_not_found", 404)
        await db.commit()
        try:
            url = await payment_service.create_payment(
                db, settings, character, vk_id, str(body.get("pack_id")), return_url,
            )
        except payment_service.PaymentError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        except Exception:
            await db.rollback()
            from loguru import logger

            logger.exception("YooKassa: не удалось создать платёж")
            return _error("Платёжный сервис не ответил. Попробуй ещё раз.", 502)
        await db.commit()
    return web.json_response({"url": url})


async def handle_yookassa_notify(request: web.Request) -> web.Response:
    """Уведомление ЮKassa. Ответ 200 всегда, кроме сбоя обработки - тогда
    ЮKassa повторит уведомление сама."""
    from bot.app_keys import SETTINGS_KEY
    from services import payment_service

    try:
        body = await request.json()
    except Exception:
        return web.Response(text="ok")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        try:
            credited = await payment_service.process_notification(db, request.app[SETTINGS_KEY], body)
            await db.commit()
        except Exception:
            await db.rollback()
            from loguru import logger

            logger.exception("YooKassa: ошибка обработки уведомления")
            return web.Response(status=500, text="retry")
    if credited is not None:
        from bot.handlers import world as world_handlers

        await world_handlers.send_plain_notice(
            credited.vk_id, f"💎 Оплата прошла: +{credited.gems} самоцветов ({credited.pack_name}). Спасибо!",
        )
    return web.Response(text="ok")


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/shop", handle_get)
    app.router.add_post("/api/miniapp/shop", handle_post)
    app.router.add_get("/api/miniapp/payments", handle_get_payments)
    app.router.add_post("/api/miniapp/payments", handle_post_payment)
    app.router.add_post("/api/yookassa/notify", handle_yookassa_notify)
