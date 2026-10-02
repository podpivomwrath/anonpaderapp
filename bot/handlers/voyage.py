"""Долгие путешествия (AFK) в чате: меню в родном городе, отправка,
ежечасные события, «Вернуться».

Пока игрок в пути, его сообщения перехватывает этот модуль раньше всех
остальных (он стоит в LABELERS сразу после онбординга): работает только
«⚓ Вернуться», на остальное - напоминание и клавиатура пути. Кто в пути -
in-memory набор peer_id, заполняется из базы при старте (load_away) и
поддерживается при уходе и возвращении.
"""

import random

from loguru import logger
from sqlalchemy import select
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import FuncRule

from bot.activity import activity_action
from bot.battle_keyboard import in_any_battle
from bot.keyboards import world as kb
from game.economy import voyage_config as vc
from models import User
from services import onboarding_service as onboarding_svc
from services import voyage_service
from services.db import get_session_factory

labeler = BotLabeler()
_bot_api = None
_rng = random.Random()
_away: set[int] = set()

AWAY = FuncRule(lambda m: m.peer_id in _away)


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def load_away() -> None:
    """При старте бота: кто сейчас в пути (переживает перезапуск)."""
    from models import Character

    async with get_session_factory()() as db:
        ids = await voyage_service.away_ids(db)
        if ids:
            vk = (await db.execute(
                select(User.vk_id).join(Character, Character.user_id == User.id).where(Character.id.in_(ids))
            )).scalars().all()
            _away.update(vk)


def is_away(peer_id: int) -> bool:
    return peer_id in _away


# --- Меню в родном городе ---


def _menu_text(character, voyage) -> str:
    trip = voyage_service.voyage_of(character)
    lines = [f"{trip.emoji} {trip.title}", ""]
    if voyage is None:
        lines.append(f"{trip.gear}: {vc.VOYAGE_PRICE} золота.")
    else:
        for part in vc.PARTS:
            emoji, name = vc.part_name(trip.region, part.id)
            level = getattr(voyage, part.id)
            cost = voyage_service.upgrade_cost(voyage, part.id)
            nxt = f" → {part.values[level]} за {cost}" if cost else " · предел"
            lines.append(f"{emoji} {name} {level}/{len(part.values)}: {part.values[level - 1]} {part.unit}{nxt}")
    lines += ["", "Раз в час - событие и небольшая награда. Вернуться можно в любой момент."]
    return "\n".join(lines)


def _menu_keyboard(character, voyage) -> str:
    trip = voyage_service.voyage_of(character)
    k = Keyboard(inline=True)
    if voyage is None:
        k.add(Text(f"Купить: {vc.VOYAGE_PRICE}", payload={"type": "voyage_buy"}), color=KeyboardButtonColor.POSITIVE)
        return k.get_json()
    k.add(Text(f"{trip.emoji} Отправиться", payload={"type": "voyage_go"}), color=KeyboardButtonColor.POSITIVE)
    for part in vc.PARTS:
        cost = voyage_service.upgrade_cost(voyage, part.id)
        if cost:
            emoji, name = vc.part_name(trip.region, part.id)
            k.row()
            k.add(Text(f"{emoji} {name}: {cost}", payload={"type": "voyage_up", "part": part.id}),
                  color=KeyboardButtonColor.SECONDARY)
    return k.get_json()


@labeler.message(text=list(kb.VOYAGE_BUTTONS.values()))
async def open_menu(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if kb.VOYAGE_BUTTONS.get(character.region) != message.text:
            await message.answer("Этот путь начинается не отсюда.")
            return
        voyage = await voyage_service.get(db, character.id)
        await db.commit()
    await message.answer(_menu_text(character, voyage), keyboard=_menu_keyboard(character, voyage))


async def _act(message: Message, action) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            done = await action(db, character)
        except voyage_service.VoyageError as exc:
            await db.rollback()
            await message.answer(str(exc))
            return
        voyage = await voyage_service.get(db, character.id)
        await db.commit()
    await message.answer(done + "\n\n" + _menu_text(character, voyage), keyboard=_menu_keyboard(character, voyage))


@labeler.message(payload_contains={"type": "voyage_buy"})
@activity_action
async def buy(message: Message) -> None:
    async def action(db, character):
        await voyage_service.buy(db, character)
        return f"Куплено: {voyage_service.voyage_of(character).gear}."
    await _act(message, action)


@labeler.message(payload_contains={"type": "voyage_up"})
@activity_action
async def upgrade(message: Message) -> None:
    part_id = (message.get_payload_json() or {}).get("part")

    async def action(db, character):
        voyage = await voyage_service.upgrade(db, character, part_id)
        emoji, name = vc.part_name(voyage.region, part_id)
        return f"{emoji} {name}: уровень {getattr(voyage, part_id)}."
    await _act(message, action)


@labeler.message(payload_contains={"type": "voyage_go"})
@activity_action
async def go(message: Message) -> None:
    from bot.handlers import pvp as pvp_handlers
    from bot.handlers import world as world_handlers

    peer_id = message.peer_id
    if in_any_battle(peer_id) or pvp_handlers.has_active_battle(peer_id) or world_handlers.is_busy(peer_id):
        await message.answer("Сначала закончи то, что начал.")
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            voyage = await voyage_service.start(db, character)
        except voyage_service.VoyageError as exc:
            await db.rollback()
            await message.answer(str(exc))
            return
        hours = voyage_service.part_value(voyage, "endurance")
        await db.commit()
    _away.add(peer_id)
    trip = vc.VOYAGES[voyage.region]
    await message.answer(
        f"{trip.start}\n\nВ пути до {hours} ч. Раз в час - весть с дороги. Вернуться можно в любой момент.",
        keyboard=kb.voyage_keyboard(),
    )


# --- В пути: перехват всего ---


@labeler.message(AWAY, text=[kb.BTN_VOYAGE_RETURN])
async def come_back(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        try:
            text = await voyage_service.come_back(db, character)
        except voyage_service.VoyageError:
            text = None
        await db.commit()
    _away.discard(peer_id)
    await _send_home(peer_id, text or "Ты дома.")


@labeler.message(AWAY)
async def while_away(message: Message) -> None:
    """Пока в пути, ничего другого: напоминание и клавиатура пути."""
    await message.answer("Ты в долгом пути. Вернуться можно кнопкой «⚓ Вернуться».", keyboard=kb.voyage_keyboard())


async def _send_home(peer_id: int, header: str) -> None:
    from bot.handlers import mounts as mounts_handlers  # экран клетки - там

    await mounts_handlers.send_cell_screen(peer_id, header)


# --- Фоновая задача ---


async def tick_job() -> None:
    """Раз в минуту: события тем, у кого подошёл час, и конец похода."""
    if _bot_api is None:
        return
    from models import Character

    try:
        async with get_session_factory()() as db:
            notices = await voyage_service.tick(db, _rng)
            peers = {}
            if notices:
                ids = {n.character_id for n in notices}
                peers = dict((await db.execute(
                    select(Character.id, User.vk_id).join(User, User.id == Character.user_id)
                    .where(Character.id.in_(ids))
                )).all())
            await db.commit()
    except Exception:
        logger.exception("Долгий путь: тик не прошёл")
        return
    from bot.handlers import stats_window

    for notice in notices:
        peer_id = peers.get(notice.character_id)
        if peer_id is None:
            continue
        try:
            if notice.finished:
                _away.discard(peer_id)
                await _send_home(peer_id, notice.text)
            else:
                await _bot_api.messages.send(
                    peer_id=peer_id, message=notice.text, random_id=0, keyboard=kb.voyage_keyboard(),
                )
                if notice.levels:
                    await stats_window.notify_levelup(peer_id, notice.levels, notice.new_level)
        except Exception:
            logger.exception("Долгий путь: не доставлено {}", peer_id)
