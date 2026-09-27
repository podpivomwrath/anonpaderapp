"""Передача предметов и валюты: переслать боту сообщение получателя с
подписью «передать <что> [сколько]».

Получатель - автор пересланного сообщения (или того, на которое ответили),
как у приглашения в группу. Передача необратима, поэтому всегда через
подтверждение; одноимённые вещи и градации руды - выбором из списка.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot import editable_message
from bot.activity import activity_action, blocked_reason
from bot.keyboards.items import no_keyboard
from services import onboarding_service, transfer_service
from services.db import get_session_factory

labeler = BotLabeler()
_bot_api = None

PENDING_TTL_SECONDS = 180
MAX_CHOICES = 8
NAMESPACE = "transfer"

USAGE_TEXT = (
    "Чтобы передать, перешли сообщение получателя с подписью:\n"
    "передать <что> <сколько>\n"
    "Например: передать золото 500, передать Малое исцеление 3, передать Скальпель Хирурга."
)


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


@dataclass
class Pending:
    token: str
    recipient_id: int
    recipient_name: str
    recipient_peer: int
    offers: list[transfer_service.Offer]
    qty: int | None
    chosen: transfer_service.Offer | None = None
    created: float = field(default_factory=time.monotonic)


_pending: dict[int, Pending] = {}


def _alive(peer_id: int) -> Pending | None:
    pending = _pending.get(peer_id)
    if pending is None or time.monotonic() - pending.created > PENDING_TTL_SECONDS:
        _pending.pop(peer_id, None)
        return None
    return pending


def _qty_text(offer: transfer_service.Offer, qty: int) -> str:
    return f" ×{qty}" if offer.stackable else ""


def _confirm_keyboard(token: str) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text("✅ Передать", payload={"type": "transfer_confirm", "t": token}), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text("Отмена", payload={"type": "transfer_cancel", "t": token}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def _choice_keyboard(token: str, count: int) -> str:
    kb = Keyboard(inline=True)
    for i in range(count):
        if i and i % 4 == 0:
            kb.row()
        kb.add(Text(str(i + 1), payload={"type": "transfer_pick", "t": token, "i": i}))
    kb.row()
    kb.add(Text("Отмена", payload={"type": "transfer_cancel", "t": token}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def _recipient_vk_id(message: Message) -> int | None:
    if message.reply_message is not None:
        return message.reply_message.from_id
    if message.fwd_messages:
        return message.fwd_messages[0].from_id
    return None


def _resolve_qty(offer: transfer_service.Offer, qty: int | None) -> tuple[int | None, str | None]:
    """(количество, текст отказа)."""
    if not offer.stackable:
        return 1, None  # экипировка - всегда одна штука, даже если написали число
    if qty is None:
        if offer.kind in ("gold", "gems"):
            return None, "Укажи сколько: например, «передать золото 500»."
        qty = 1
    if qty <= 0:
        return None, "Количество должно быть больше нуля."
    if qty > offer.available:
        return None, f"У тебя только {offer.available}."
    return qty, None


async def _ask_confirm(peer_id: int, pending: Pending) -> None:
    offer = pending.chosen
    qty, refusal = _resolve_qty(offer, pending.qty)
    if refusal:
        _pending.pop(peer_id, None)
        await editable_message.send_or_edit(_bot_api, NAMESPACE, peer_id, refusal, no_keyboard())
        return
    pending.qty = qty
    text = f"📦 Передать {offer.label}{_qty_text(offer, qty)} игроку {pending.recipient_name}?\nЭто не отменить."
    await editable_message.send_or_edit(_bot_api, NAMESPACE, peer_id, text, _confirm_keyboard(pending.token))


@labeler.message(regex=r"(?is)^\s*/?передать(?:\s+(.*))?$")
@activity_action
async def transfer_command(message: Message, match: tuple) -> None:
    peer_id = message.peer_id
    request = (match[0] or "").strip() if match else ""
    recipient_vk = _recipient_vk_id(message)
    if not request or recipient_vk is None:
        await message.answer(USAGE_TEXT)
        return
    if recipient_vk <= 0:
        await message.answer("Передать можно только игроку.")
        return
    async with get_session_factory()() as db:
        sender = await onboarding_service.get_character(db, message.from_id)
        if sender is None or sender.creation_state is not None:
            return
        reason = await blocked_reason(db, sender, peer_id)
        if reason:
            await message.answer(reason)
            return
        recipient = await onboarding_service.get_character(db, recipient_vk)
        if recipient is None or recipient.creation_state is not None:
            await message.answer("У этого человека нет персонажа в игре.")
            return
        if recipient.id == sender.id:
            await message.answer("Самому себе не передать.")
            return
        name, qty = transfer_service.parse(request)
        lookup = await transfer_service.find(db, sender.id, name, qty)
        await db.commit()

    if not lookup.offers:
        await message.answer(lookup.refusal or f"У тебя нет «{name}».")
        return
    pending = Pending(
        token=uuid.uuid4().hex[:10], recipient_id=recipient.id, recipient_name=recipient.name,
        recipient_peer=recipient_vk, offers=lookup.offers[:MAX_CHOICES], qty=qty,
    )
    _pending[peer_id] = pending
    editable_message.clear(NAMESPACE, peer_id)
    if len(pending.offers) == 1:
        pending.chosen = pending.offers[0]
        await _ask_confirm(peer_id, pending)
        return
    lines = ["Какой именно?", ""] + [f"{i}. {o.label}" + (f" - {o.available} шт." if o.stackable else "")
                                     for i, o in enumerate(pending.offers, start=1)]
    await editable_message.send_or_edit(
        _bot_api, NAMESPACE, peer_id, "\n".join(lines), _choice_keyboard(pending.token, len(pending.offers)),
    )


@labeler.message(payload_contains={"type": "transfer_pick"})
async def transfer_pick(message: Message) -> None:
    payload = message.get_payload_json() or {}
    pending = _alive(message.peer_id)
    if pending is None or payload.get("t") != pending.token:
        await message.answer("Эта передача уже неактуальна.")
        return
    index = payload.get("i")
    if not isinstance(index, int) or not 0 <= index < len(pending.offers):
        return
    pending.chosen = pending.offers[index]
    await _ask_confirm(message.peer_id, pending)


@labeler.message(payload_contains={"type": "transfer_cancel"})
async def transfer_cancel(message: Message) -> None:
    pending = _alive(message.peer_id)
    if pending is not None and (message.get_payload_json() or {}).get("t") == pending.token:
        _pending.pop(message.peer_id, None)
    await editable_message.send_or_edit(_bot_api, NAMESPACE, message.peer_id, "Передача отменена.", no_keyboard())


@labeler.message(payload_contains={"type": "transfer_confirm"})
@activity_action
async def transfer_confirm(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    pending = _alive(peer_id)
    if pending is None or payload.get("t") != pending.token or pending.chosen is None:
        await message.answer("Эта передача уже неактуальна.")
        return
    # Снимаем ДО исполнения: второе нажатие не найдёт, что подтверждать.
    _pending.pop(peer_id, None)
    offer, qty = pending.chosen, pending.qty or 1
    async with get_session_factory()() as db:
        sender = await onboarding_service.get_character(db, message.from_id)
        if sender is None:
            return
        reason = await blocked_reason(db, sender, peer_id)
        if reason:
            await message.answer(reason)
            return
        try:
            moved = await transfer_service.execute(db, sender.id, pending.recipient_id, offer, qty)
        except transfer_service.TransferFailed as exc:
            await db.rollback()
            await editable_message.send_or_edit(_bot_api, NAMESPACE, peer_id, str(exc), no_keyboard())
            return
        await db.commit()
        sender_name = sender.name

    what = f"{offer.label}{_qty_text(offer, moved)}"
    await editable_message.send_or_edit(
        _bot_api, NAMESPACE, peer_id, f"📦 Передано игроку {pending.recipient_name}: {what}.", no_keyboard(),
    )
    try:
        await _bot_api.messages.send(
            peer_id=pending.recipient_peer, random_id=0, message=f"📦 {sender_name} передаёт тебе: {what}.",
        )
    except Exception:  # noqa: BLE001 - получатель мог запретить сообщения; передача уже состоялась
        logger.warning("Передача: не удалось уведомить получателя {}", pending.recipient_peer)
