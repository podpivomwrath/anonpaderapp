"""Курьер (2026-10-19): фоновый бег по клеткам и сообщения о посылке.

Логика - services/courier_service.py. Здесь - кто в бою (это знает только
бот), шаги раз в пару секунд и что сказать отправителю и получателю.
"""

import time

from loguru import logger
from sqlalchemy import select

from game.economy import courier_config as cc
from models import Character, CourierDelivery, User
from services import courier_service
from services.db import get_session_factory

_bot_api = None
#: id персонажа -> когда последний раз видели его в бою (time.monotonic)
_last_busy: dict[int, float] = {}
AFTER_BATTLE_SECONDS = 4.0


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _what(d: CourierDelivery) -> str:
    # У пачки количества уже в подписи (courier_service.send_batch).
    return f"{d.label}" + (f" ×{d.amount}" if d.kind in ("elixir", "ore", "herb", "food") else "")


async def _busy_ids(db) -> set[int]:
    """Получатели посылок, которые сейчас в бою или рейде: им курьер не отдаёт."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import raid_combat

    rows = (await db.execute(
        select(Character.id, User.vk_id).join(User, User.id == Character.user_id)
        .join(CourierDelivery, CourierDelivery.recipient_id == Character.id)
        .where(CourierDelivery.status == courier_service.ACTIVE)
    )).all()
    now = time.monotonic()
    busy = set()
    for cid, vk in rows:
        if vk is not None and (in_any_battle(vk) or raid_combat.has_active_raid(cid)):
            _last_busy[cid] = now
        # Бой кончился только что - пусть сначала придут итог боя и сводка
        # клетки, а сообщение курьера - после них.
        if now - _last_busy.get(cid, -AFTER_BATTLE_SECONDS) < AFTER_BATTLE_SECONDS:
            busy.add(cid)
    return busy


async def _peer(db, character_id: int | None) -> int | None:
    if character_id is None:
        return None
    return await db.scalar(
        select(User.vk_id).join(Character, Character.user_id == User.id).where(Character.id == character_id)
    )


async def _send(peer_id: int | None, text: str) -> None:
    if peer_id is None:
        return
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0)
    except Exception:
        logger.warning("Курьер: сообщение не доставлено {}", peer_id)


async def tick_job() -> None:
    if _bot_api is None:
        return
    try:
        async with get_session_factory()() as db:
            events = await courier_service.advance(db, await _busy_ids(db))
            notices = []
            for event in events:
                d = event.delivery
                sender = await db.get(Character, d.sender_id) if d.sender_id else None
                notices.append((event.kind, d, sender.name if sender else None,
                                await _peer(db, d.sender_id), await _peer(db, d.recipient_id)))
            await db.commit()
    except Exception:
        logger.exception("Курьер: шаг не прошёл")
        return
    for kind, d, sender_name, sender_peer, recipient_peer in notices:
        what = _what(d)
        from_whom = f" от {sender_name}" if d.reveal_sender and sender_name else ""
        if d.sender_id == d.recipient_id:
            # Покупки с рынка (2026-10-24): курьер несёт игроку его же ящик.
            if kind == "delivered":
                await _send(recipient_peer, f"📦 Курьер принёс покупки с рынка: {what}.")
            continue
        if kind == "picked":
            await _send(sender_peer, f"{cc.EMOJI} Курьер забрал посылку ({what}) и побежал к получателю.")
            await _send(recipient_peer, f"{cc.EMOJI} К тебе бежит курьер с посылкой{from_whom}: {what}.")
        elif kind == "delivered":
            await _send(recipient_peer, f"📦 Курьер отдаёт тебе посылку{from_whom}: {what}.")
            await _send(sender_peer, f"{cc.EMOJI} Курьер доставил посылку ({what}) и пошёл домой.")
        elif kind == "returned":
            await _send(sender_peer, f"{cc.EMOJI} Получателя больше нет в игре. Курьер вернул посылку: {what}.")
