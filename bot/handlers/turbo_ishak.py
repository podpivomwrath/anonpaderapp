"""Турбоишак дня (2026-10-19): кнопка «Подойти», поимка, имя, фоновый бег.

Правила - game/world/turbo_ishak.py, запись - services/turbo_ishak_service.py.
"""

import asyncio
import random

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import FuncRule

from bot import turbo_texts as texts
from bot.activity import activity_action, blocked_reason
from bot.vk_media import photo_attachment
from game.economy import turbo_config as tc
from game.world import scene_events as se
from services import mount_service, onboarding_service
from services import turbo_ishak_service as svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True

_bot_api = None
_rng = random.Random()
#: Кто поймал ишака и ещё не назвал: следующее сообщение - имя.
_naming: set[int] = set()
_tasks: set[asyncio.Task] = set()


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def load_naming() -> None:
    """После перезапуска бот всё ещё ждёт имя от тех, кто его не дал."""
    async with get_session_factory()() as db:
        _naming.update(await svc.awaiting_name(db))
        await db.rollback()


async def _send(peer_id: int, text: str, **kwargs) -> None:
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, **kwargs)
    except Exception:
        logger.warning("Турбоишак: сообщение не доставлено {}", peer_id)


def _photo(image: str) -> str | None:
    return photo_attachment(image) if image else None


def approach_keyboard(label: str) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(label, payload={"type": "turbo_approach"}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def skip_name_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(texts.BTN_SKIP_NAME, payload={"type": "turbo_skip_name"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


async def _offer(peer_id: int, character, text: str) -> None:
    """Сообщение с кнопкой «Подойти» и шансом на ней - если подойти можно."""
    async with get_session_factory()() as db:
        day = await svc.active(db)
        reason = svc.can_approach_reason(character, day, await svc.owns_turbo(db, character.id), svc._now())
        if reason is not None:
            await db.rollback()
            return
        stat, chance = await svc.catch_chance(db, character)
        await db.rollback()
    label = texts.approach_label(se.STAT_EMOJI[stat], chance)
    await _send(peer_id, text, keyboard=approach_keyboard(label), attachment=_photo(tc.HERE_IMAGE))


async def maybe_send_here_button(peer_id: int, character) -> None:
    """Вход на клетку, где стоит ишак (зовёт world.send_cell_buttons)."""
    await _offer(peer_id, character, texts.HERE_TEXT)


@labeler.message(payload_contains={"type": "turbo_approach"})
@activity_action
async def approach(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        reason = await blocked_reason(db, character, peer_id)
        if reason:
            await message.answer(reason)
            return
        result = await svc.attempt(db, character, _rng)
        name = character.name
        await db.commit()
    if result.outcome == "caught":
        _naming.add(peer_id)
        await message.answer(texts.CAUGHT_TEXT, attachment=_photo(tc.CAUGHT_IMAGE))
        await message.answer(texts.ASK_NAME_TEXT, keyboard=skip_name_keyboard())
        task = asyncio.create_task(_news(peer_id, name))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return
    if result.outcome == "ran":
        await message.answer(texts.RAN_TEXT)
        return
    await message.answer(texts.REFUSALS.get(result.outcome, texts.REFUSALS["gone"]))


async def _news(catcher_peer: int, player: str) -> None:
    async with get_session_factory()() as db:
        recipients = await svc.news_recipients(db)
        await db.rollback()
    text = texts.CAUGHT_NEWS.format(player=player)
    for peer_id in recipients:
        if peer_id == catcher_peer:
            continue
        await _send(peer_id, text)
        await asyncio.sleep(0.05)  # лимит сообщений сообщества


async def _spawn_news() -> None:
    """Ишак выбежал - всем, кто заходил за SPAWN_NEWS_ACTIVE_HOURS, без координат."""
    async with get_session_factory()() as db:
        recipients = await svc.news_recipients(db, hours=tc.SPAWN_NEWS_ACTIVE_HOURS)
        await db.rollback()
    logger.info("Турбоишак: оповещаю о выходе {}", len(recipients))
    for peer_id in recipients:
        await _send(peer_id, texts.SPAWN_NEWS, attachment=_photo(tc.HERE_IMAGE))
        await asyncio.sleep(0.05)  # лимит сообщений сообщества


@labeler.message(payload_contains={"type": "turbo_skip_name"})
async def skip_name(message: Message) -> None:
    peer_id = message.peer_id
    if peer_id not in _naming:
        return
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None:
            return
        await svc.skip_name(db, character)
        await db.commit()
    _naming.discard(peer_id)
    await message.answer(texts.SKIPPED_NAME_TEXT)


@labeler.message(FuncRule(lambda m: m.peer_id in _naming and m.peer_id == m.from_id and not m.payload))
async def name_reply(message: Message) -> None:
    """Имя пойманному ишаку - следующим сообщением в личке."""
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None:
            return
        try:
            await svc.set_name(db, character, message.text)
        except svc.TurboError as exc:
            await db.rollback()
            await message.answer(f"{exc} Попробуй ещё раз.", keyboard=skip_name_keyboard())
            return
        owned = {m.mount_id: m.name for m in await mount_service.owned_mounts(db, character.id)}
        await db.commit()
    _naming.discard(peer_id)
    await message.answer(texts.NAMED_TEXT.format(name=owned.get(tc.MOUNT_ID, "Турбоишак")))


# --- Фоновая задача ---


async def tick_job() -> None:
    """Раз в 20 секунд: выпустить, перегнать, закончить. Прибежал на клетку,
    где кто-то стоит, - тем сразу кнопка."""
    if _bot_api is None:
        return
    try:
        async with get_session_factory()() as db:
            events = await svc.tick(db, _rng)
            await db.commit()
    except Exception:
        logger.exception("Турбоишак: тик не прошёл")
        return
    for event in events:
        day = event.day
        if event.kind == "spawn":
            logger.info("Турбоишак {}: выбежал на ({};{})", day.day, day.x, day.y)
            task = asyncio.create_task(_spawn_news())
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)
        if event.kind not in ("spawn", "arrive"):
            continue
        await _notify_cell(day.x, day.y)


async def _notify_cell(x: int, y: int) -> None:
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import voyage

    async with get_session_factory()() as db:
        here = await svc.peers_on_cell(db, x, y)
        await db.rollback()
    for peer_id, character in here:
        if in_any_battle(peer_id) or voyage.is_away(peer_id):
            continue
        await _offer(peer_id, character, texts.ARRIVED_TEXT)
