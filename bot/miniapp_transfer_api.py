"""Передача по нику из мини-аппа (2026-10-22, просьба владельца).

В чате получатель берётся из ответа на его сообщение («/передать ...» в
ответ игроку), то есть нужен его профиль VK. Здесь получателя называют по
нику. Всё остальное - как в чате (bot/handlers/transfer.py): что передать,
ищет transfer_service.find по той же команде, которую копирует кнопка
«Команда передачи»; вещи, зелья и руду из рук в руки - только на одной
клетке, дальше - курьер; налог с валюты, журнал передач, весть получателю
(ник отправителя - только своим по гильдии).

Два шага: без confirm - проверка и строка «что и кому», ничего не меняется;
с confirm - передача.
"""

from aiohttp import web
from loguru import logger
from sqlalchemy import func, select

from bot import miniapp_api
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from models import Character, User
from services import transfer_service

COMMAND = "/передать"


def _bad(text: str, status: int = 400) -> web.Response:
    return web.json_response({"error": text}, status=status)


async def handle_post_transfer(request: web.Request) -> web.Response:
    from bot.activity import blocked_reason
    from bot.handlers import transfer as chat
    from game.economy import courier_config as cc

    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return _bad("bad_request")
    if not isinstance(body, dict):
        return _bad("bad_request")
    command = str(body.get("command") or "").strip()
    nick = str(body.get("name") or "").strip()
    qty = body.get("qty")
    confirm = bool(body.get("confirm"))
    if not command.lower().startswith(COMMAND) or not nick:
        return _bad("Впиши ник получателя.")
    if qty is not None and (not isinstance(qty, int) or isinstance(qty, bool)):
        return _bad("bad_request")

    async with request.app[SESSION_FACTORY_KEY]() as db:
        sender = await miniapp_api._load_character(db, vk_user_id)
        if sender is None:
            return _bad("character_not_found", 404)
        reason = await blocked_reason(db, sender, vk_user_id)
        if reason:
            return _bad(reason, 409)
        row = (await db.execute(
            select(Character, User.vk_id).join(User, User.id == Character.user_id)
            .where((Character.name == nick) | (func.lower(Character.name) == nick.lower()),
                   Character.creation_state.is_(None))
        )).first()
        if row is None:
            return _bad(f"Игрока с ником «{nick}» нет.", 404)
        recipient, recipient_vk = row
        # Ники - сразу: после rollback/commit поля персонажа уже не прочитать.
        recipient_name, sender_name = recipient.name, sender.name
        if recipient.id == sender.id:
            return _bad("Самому себе не передать.")

        name, number = transfer_service.parse(command[len(COMMAND):].strip())
        lookup = await transfer_service.find(db, sender.id, name, number)
        if not lookup.offers:
            return _bad(lookup.refusal or "Этого у тебя уже нет.")
        if len(lookup.offers) > 1:
            return _bad("Под это название подходит несколько вещей - передай из карточки нужной.")
        offer = lookup.offers[0]
        # У экипировки число в команде - номер вещи, у стаков - количество.
        amount, refusal = chat._resolve_qty(offer, qty if offer.stackable else None)
        if refusal:
            return _bad(refusal)
        courier = transfer_service.needs_courier(offer, sender, recipient)
        if courier and not sender.has_courier:
            return _bad(chat.NO_COURIER_TEXT)
        what = f"{offer.label}{chat._qty_text(offer, amount)}"
        if not confirm:
            await db.rollback()
            return web.json_response({"preview": {
                "what": what, "to": recipient_name, "courier": courier,
            }})

        reveal = sender.guild_id is not None and sender.guild_id == recipient.guild_id
        try:
            if courier:
                from services import courier_service

                await courier_service.send(db, sender, recipient, offer, amount, reveal)
            else:
                amount = await transfer_service.execute(db, sender.id, recipient.id, offer, amount)
        except Exception as exc:
            from services import courier_service

            if not isinstance(exc, (transfer_service.TransferFailed, courier_service.CourierError)):
                raise
            await db.rollback()
            return _bad(str(exc))
        await db.commit()

    if courier:
        # Получатель узнает, когда курьер заберёт посылку (bot/handlers/courier.py).
        return web.json_response({"done": f"{cc.EMOJI} Курьер выбежал из твоего города за посылкой для {recipient_name}: {what}."})
    note = f"📦 {sender_name} передаёт тебе: {what}." if reveal else f"📦 Тебе передали: {what}."
    if chat._bot_api is not None:
        try:
            await chat._bot_api.messages.send(peer_id=recipient_vk, random_id=0, message=note)
        except Exception:  # noqa: BLE001 - получатель мог закрыть сообщения; передача уже состоялась
            logger.warning("Передача по нику: не удалось уведомить получателя {}", recipient_vk)
    return web.json_response({"done": f"📦 Передано игроку {recipient_name}: {what}."})


def register_routes(app: web.Application) -> None:
    app.router.add_post("/api/miniapp/transfer", handle_post_transfer)
