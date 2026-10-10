"""Разломы в чате: сообщение на клетке, вход с ожиданием 60 секунд, отмена,
запуск боя. Сам бой - bot/handlers/raid_combat.py, как у рейдов.

Пока группа ждёт у входа, её сообщения перехватывает этот модуль (стоит в
LABELERS сразу после долгого пути): кнопок нет, кроме «Отменить вход» и
профиля. Пропускается всё, что нужно, чтобы отбиться: бой, /напасть,
«Осмотреться», вступление в чужой бой. Ожидание не обновляет сообщение
по секундам - решение владельца, без лишней нагрузки.
"""

import random

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import FuncRule

from bot import rift_texts as texts
from bot.activity import activity_action, blocked_reason
from bot.battle_keyboard import in_any_battle

from bot.keyboards.world import BTN_LOOK_AROUND, add_miniapp_button
from models import Character
from services import death_service, group_service, rift_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
_bot_api = None
_rng = random.Random()
#: peer_id -> id разлома, у входа которого он ждёт. После перезапуска
#: ожидания нет (rift_service.recover), поэтому память здесь честная.
_waiting: dict[int, int] = {}


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def is_waiting(peer_id: int) -> bool:
    return peer_id in _waiting


def _passes_through(message: Message) -> bool:
    """Чем можно пользоваться у входа: отбиться и оглядеться."""
    from bot.handlers import pvp

    if in_any_battle(message.peer_id) or message.peer_id in pvp._pending_join_prompt:
        return True
    text = (message.text or "").strip().lower()
    if text.startswith(("/напасть", "/attack")) or message.text == BTN_LOOK_AROUND:
        return True
    payload = message.get_payload_json() or {}
    return isinstance(payload, dict) and str(payload.get("type", "")).startswith("pvp")


WAITING = FuncRule(lambda m: m.peer_id in _waiting and not _passes_through(m))


def waiting_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text(texts.BTN_CANCEL), color=KeyboardButtonColor.NEGATIVE)
    add_miniapp_button(kb)
    return kb.get_json()


def _enter_keyboard(rift_id: int) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text("🌀 Войти", payload={"type": "rift_enter", "rift": rift_id}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


async def _send(peer_id: int, text: str, **kw) -> None:
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, **kw)
    except Exception:
        logger.exception("Разлом: не доставлено {}", peer_id)


async def _send_hub(character_id: int, peer_id: int, header: str | None = None) -> None:
    """Обратно в базовый хаб клетки: сводка и клавиатура перемещения."""
    from bot.handlers import world as world_handlers

    try:
        async with get_session_factory()() as db:
            character = await db.get(Character, character_id)
            if character is None:
                return
            text, attachment, keyboard = await world_handlers.location_summary_parts(db, character, peer_id)
        if header:
            text = f"{header}\n\n{text}"
        await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0, attachment=attachment, keyboard=keyboard,
        )
    except Exception:
        logger.exception("Разлом: не удалось вернуть в хаб {}", peer_id)


async def _peers(db, character_ids: list[int]) -> dict[int, int]:
    peers = {}
    for cid in character_ids:
        peer = await onboarding_svc.vk_id_for_character(db, cid)
        if peer is not None:
            peers[cid] = peer
    return peers


# --- Клетка разлома -----------------------------------------------------------


async def maybe_send_here_button(peer_id: int, character) -> None:
    """При входе на клетку: что за разлом и кнопка «Войти». Молчит, если
    разлома нет. Без рассылки - разлом находят сами."""
    async with get_session_factory()() as db:
        rift = await rift_service.rift_at(db, character.pos_x, character.pos_y)
    if rift is None:
        return
    if rift.state != rift_service.FREE:
        await _send(peer_id, texts.busy_text(rift))
        return
    text = texts.here_text(rift, rift_service.minutes_left(rift))
    if not rift_service.level_fits(character.level, rift):
        lo, hi = rift_service.band(rift)
        await _send(peer_id, f"{text}\n\n🔒 Тебе не по уровню: разлом для {lo}-{hi}.")
        return
    await _send(peer_id, text, keyboard=_enter_keyboard(rift.id),
                attachment=texts.RiftTexts(rift.kind).prologue_attachment())


# --- Вход ---------------------------------------------------------------------


@labeler.message(payload_contains={"type": "rift_enter"})
@activity_action
async def enter(message: Message) -> None:
    peer_id = message.peer_id
    rift_id = (message.get_payload_json() or {}).get("rift")
    if not isinstance(rift_id, int):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        group = await group_service.get_group_snapshot(db, character.id)
        if group is not None and group.leader_character_id != character.id:
            await message.answer("Ввести группу в разлом может только лидер группы.")
            return
        members = group.members if group is not None else [character]
        peers = await _peers(db, [c.id for c in members])
        for member in members:
            peer = peers.get(member.id)
            reason = await blocked_reason(db, member, peer) if peer is not None else "недоступен"
            if reason is None and peer in _waiting:
                reason = "уже ждёт у разлома"
            if reason is None and _busy_elsewhere(peer, member):
                reason = "занят"
            if reason:
                who = "Тебе" if member.id == character.id else member.name
                await message.answer(f"Вход невозможен - {who}: {reason}")
                return
        try:
            rift = await rift_service.begin_wait(db, rift_id, members, group.id if group else None)
        except rift_service.RiftError as exc:
            await db.rollback()
            await message.answer(str(exc))
            return
        await db.commit()
        text = texts.wait_text(rift)
    for cid, peer in peers.items():
        _waiting[peer] = rift_id
        await _send(peer, text, keyboard=waiting_keyboard())


def _busy_elsewhere(peer_id: int, character) -> bool:
    from bot.handlers import raid_combat, voyage

    return voyage.is_away(peer_id) or raid_combat.has_active_raid(character.id)


@labeler.message(FuncRule(lambda m: m.peer_id in _waiting), text=[texts.BTN_CANCEL])
async def cancel(message: Message) -> None:
    rift_id = _waiting.get(message.peer_id)
    if rift_id is None:
        return
    async with get_session_factory()() as db:
        members = await rift_service.cancel_wait(db, rift_id)
        await db.commit()
        peers = await _peers(db, members)
    for peer in [message.peer_id, *peers.values()]:
        _waiting.pop(peer, None)
    for cid, peer in peers.items():
        await _send_hub(cid, peer, texts.CANCELLED_TEXT)


@labeler.message(WAITING)
async def while_waiting(message: Message) -> None:
    await message.answer(texts.WAITING_REMINDER, keyboard=waiting_keyboard())


# --- Фоновая задача -----------------------------------------------------------


async def tick_job() -> None:
    """Раз в несколько секунд: чистка очереди (погибшие и ушедшие),
    запуск тех, у кого вышли 60 секунд, исчезновение свободных разломов."""
    if _bot_api is None:
        return
    try:
        await _prune_waits()
        async with get_session_factory()() as db:
            due = await rift_service.due_waits(db)
        for rift_id in due:
            await _start(rift_id)
        async with get_session_factory()() as db:
            await rift_service.expire_due(db)
            await db.commit()
    except Exception:
        logger.exception("Разломы: тик не прошёл")


def _gone(character: Character, rift) -> bool:
    return (
        death_service.is_dead(character)
        or (character.pos_x, character.pos_y) != (rift.x, rift.y)
        or character.travel_target_x is not None
    )


async def _prune_waits() -> None:
    """Погиб в стычке у входа или ушёл (например, с карты мини-аппа) - из
    очереди выбыл. Никого не осталось - разлом свободен для других."""
    from models import Rift
    from sqlalchemy import select

    async with get_session_factory()() as db:
        rows = (await db.scalars(select(Rift).where(
            Rift.status == rift_service.ACTIVE, Rift.state == rift_service.WAITING,
        ))).all()
        snapshot = [(r.id, r.x, r.y, list(r.members or [])) for r in rows]
    for rift_id, x, y, members in snapshot:
        async with get_session_factory()() as db:
            rift = await rift_service.lock(db, rift_id)
            if rift is None or rift.state != rift_service.WAITING:
                continue
            gone = []
            for cid in members:
                character = await db.get(Character, cid)
                peer = await onboarding_svc.vk_id_for_character(db, cid)
                if peer is not None and in_any_battle(peer):
                    continue  # отбивается - решится по итогу боя
                if character is None or _gone(character, rift):
                    gone.append(cid)
            if not gone:
                continue
            left = await rift_service.drop_members(db, rift_id, gone)
            await db.commit()
            gone_peers = await _peers(db, gone)
        for cid, peer in gone_peers.items():
            _waiting.pop(peer, None)
        if left is None:
            logger.info("Разлом {}: у входа никого не осталось", rift_id)


async def _start(rift_id: int) -> None:
    from bot.handlers import group_combat as group_combat_handlers
    from bot.handlers import raid_combat as raid_combat_handlers

    async with get_session_factory()() as db:
        rift = await rift_service.lock(db, rift_id)
        if rift is None or rift.state != rift_service.WAITING:
            return
        peers = await _peers(db, list(rift.members or []))
        if any(in_any_battle(peer) for peer in peers.values()):
            return  # у входа идёт бой - ждём его конца, следующий тик
        characters = [c for c in [await db.get(Character, cid) for cid in rift.members or []] if c is not None]
        present = [c for c in characters if not _gone(c, rift)]
        if not present:
            await rift_service.cancel_wait(db, rift_id)
            await db.commit()
            for peer in peers.values():
                _waiting.pop(peer, None)
            return
        await rift_service.start_run(db, rift, present)
        inputs = await group_combat_handlers.build_member_inputs(db, present)
        await db.commit()
        group_id = rift.group_id
    for peer in peers.values():
        _waiting.pop(peer, None)
    try:
        await raid_combat_handlers.start_raid(group_id, inputs, _rng, rift=rift)
    except Exception:
        logger.exception("Разлом {}: бой не начался", rift_id)
        async with get_session_factory()() as db:
            await rift_service.finish_run(db, rift_id, cleared=False)
            await db.commit()
        for cid, peer in peers.items():
            await _send_hub(cid, peer, "Разлом дрогнул и закрылся. Попробуйте ещё раз.")


async def recover_on_start() -> None:
    """При старте бота: держатели разломов - обратно в хаб."""
    async with get_session_factory()() as db:
        affected = await rift_service.recover(db)
        await db.commit()
        peers = await _peers(db, affected)
    for cid, peer in peers.items():
        await _send_hub(cid, peer, texts.RESTART_TEXT)
