"""Горное дело (патч 59): экран рудника, добыча, инвентарь руды.

Вход как у озера и Монолита: инлайн-кнопка при ВХОДЕ на клетку плюс команда
«Рудник». Обычное исследование на клетке рудника продолжает работать.

Главное отличие от рыбалки: добыча БЛОКИРУЕТ все действия до конца (см.
bot/activity.py::blocked_reason). Ограничителя, кроме времени, у горного дела
нет — руду нельзя продать, носить можно сколько угодно, провалов не бывает.
Единственное, что может случиться за эти минуты, — нападение другого игрока.
"""

import random

from vkbottle.bot import BotLabeler, Message

from bot import mining_texts as mt
from bot.activity import activity_action, blocked_reason
from bot.keyboards import mining as kb
from bot.keyboards.world import movement_keyboard
from game.world.scheduler import PeerScheduler
from services import mining_service, mount_service, screen_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_rng = random.Random()

#: Окончание добычи приходит отдельным сообщением по таймеру — тот же
#: механизм, что у поклёвки, прибытия и исследования.
_dig_scheduler: PeerScheduler | None = None

# Экран рудника — вложенный, родитель корневой (карта), как у озера.
screen_service.PARENT["mine"] = None


def setup(bot_api, scheduler: PeerScheduler | None = None) -> None:
    global _bot_api, _dig_scheduler
    _bot_api = bot_api
    _dig_scheduler = scheduler


def _schedule_finish(peer_id: int, seconds: float) -> None:
    if _dig_scheduler is not None:
        _dig_scheduler.schedule(peer_id, max(seconds, 1.0))


def _cancel_finish(peer_id: int) -> None:
    if _dig_scheduler is not None:
        _dig_scheduler.cancel(peer_id)


async def on_dig_done(peer_id: int) -> None:
    """Сработал таймер: выдаём руду и возвращаем обычную клавиатуру рудника."""
    if _bot_api is None:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or not mining_service.is_digging(character):
            return
        if not mining_service.dig_finished(character):
            # Таймер сработал раньше срока (перепланирование, рассинхрон) —
            # не выдаём руду досрочно, просто переставляем будильник.
            _schedule_finish(peer_id, mining_service.remaining_seconds(character))
            return
        if character.screen != "mine":
            # Страховка от того же класса ошибок: руду получает только тот,
            # кто реально стоит в забое. Если игрока вынесло наружу (рестарт
            # бота, любая будущая ветка выхода) — добыча остаётся висеть и
            # завершится, когда он вернётся в жилу.
            return
        result = await mining_service.finish_dig(db, character, _rng)
        mine = mining_service.mine_at(character)
        left = await mining_service.ore_in_mine(db, mine.id) if mine else 0
        on_mine_screen = character.screen == "mine"
        await db.commit()

    if result is None:
        return
    text = mt.dig_result_text(result)
    keyboard = kb.mine_keyboard(left > 0) if on_mine_screen else None
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0, keyboard=keyboard,
    )


async def _enter_mine(message: Message) -> None:
    """Открывает экран рудника. Общая точка для кнопки и команды «Рудник»."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mine = mining_service.mine_at(character)
        if mine is None:
            # Вне рудника команда МОЛЧИТ: слово может встретиться в разговоре.
            return

        # Своя же незаконченная добыча в ЭТОМ руднике — не повод отказывать во
        # входе, наоборот: вернуться и доработать остаток это и есть правило
        # статичных жил. Поэтому общий гейт проверяем только когда не копаем.
        digging_here = (
            mining_service.is_digging(character)
            and character.mining_mine_id == mine.id
        )
        if not digging_here:
            reason = await blocked_reason(db, character, message.peer_id)
            if reason:
                await message.answer(reason)
                return

        await screen_service.set_screen(db, character, "mine")
        ore_left = await mining_service.ore_in_mine(db, mine.id)
        remaining = mining_service.remaining_seconds(character)
        await db.commit()

    if digging_here:
        if remaining <= 0:
            await on_dig_done(message.peer_id)
            return
        _schedule_finish(message.peer_id, remaining)
        await message.answer(
            mt.dig_progress_text(remaining), keyboard=kb.digging_keyboard()
        )
        return

    text = (
        mt.mine_intro(mine, _rng, ore_left) + chr(10) * 2
        + mt.SEP + chr(10) + mt.level_line(character) + chr(10) + mt.SEP
    )
    await message.answer(text, keyboard=kb.mine_keyboard(ore_left > 0))


@labeler.message(text=[mt.MINE_COMMAND])
@activity_action
async def mine_command(message: Message) -> None:
    await _enter_mine(message)


@labeler.message(payload_contains={"type": "approach_mine"})
@activity_action
async def mine_button(message: Message) -> None:
    await _enter_mine(message)


@labeler.message(text=[mt.BTN_DIG])
@activity_action
async def dig(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "mine":
            return
        mine = mining_service.mine_at(character)
        if mine is None:
            await message.answer(mt.NOT_AT_MINE_TEXT)
            return
        if mining_service.is_digging(character):
            await message.answer(
                mt.dig_progress_text(mining_service.remaining_seconds(character)),
                keyboard=kb.digging_keyboard(),
            )
            return

        started = await mining_service.start_dig(db, character, mine, _rng)
        if started is None:
            await db.commit()
            await message.answer(mt.EMPTY_MINE_TEXT, keyboard=kb.mine_keyboard(False))
            return
        await db.commit()

    _schedule_finish(message.peer_id, started.seconds)
    await message.answer(
        mt.dig_started_text(started.seconds, started.resumed),
        keyboard=kb.digging_keyboard(),
    )


@labeler.message(text=[mt.BTN_ABANDON])
@activity_action
async def abandon(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "mine":
            return
        if not mining_service.is_digging(character):
            await message.answer(mt.NOT_DIGGING_TEXT)
            return
        mining_service.abandon_dig(character)
        mine = mining_service.mine_at(character)
        left = await mining_service.ore_in_mine(db, mine.id) if mine else 0
        await db.commit()
    _cancel_finish(message.peer_id)
    await message.answer(mt.ABANDONED_TEXT, keyboard=kb.mine_keyboard(left > 0))


@labeler.message(text=[mt.BTN_ORE])
@activity_action
async def ore_inventory(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "mine":
            return
        rows = await mining_service.get_ore(db, character.id)
    await message.answer(mt.ore_screen(rows), keyboard=kb.ore_keyboard())


@labeler.message(text=[mt.BTN_LEAVE_MINE])
@activity_action
async def leave_mine(message: Message) -> None:
    """Выход наверх с экрана рудника.

    С незаконченной добычей выйти НЕЛЬЗЯ — сначала бросить кирку. Раньше было
    можно, и это давало руду человеку, стоящему снаружи: выход не отменял
    добычу (чтобы можно было вернуться и доработать), но и таймер завершения
    не снимал, так что тот исправно срабатывал «дистанционно».

    Кнопки такой в забое больше нет, но текст можно набрать руками — поэтому
    проверка стоит здесь, в обработчике, а не только в раскладке клавиатуры.
    """
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        if mining_service.is_digging(character):
            await message.answer(
                mt.LEAVE_WHILE_DIGGING_TEXT, keyboard=kb.digging_keyboard()
            )
            return
        await screen_service.set_screen(db, character, None)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()
    _cancel_finish(message.peer_id)
    await message.answer(
        "Ты поднимаешься наверх.",
        keyboard=movement_keyboard(
            character.pos_x, character.pos_y, message.peer_id, has_mount
        ),
    )


@labeler.message(payload_contains={"type": "dig_vein"})
@activity_action
async def dig_event_vein(message: Message) -> None:
    """Мелкая жила из исследования: добыча прямо из события, без экрана."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if mining_service.is_digging(character):
            await message.answer(mt.ALREADY_DIGGING_TEXT)
            return
        reason = await blocked_reason(db, character, message.peer_id)
        if reason:
            await message.answer(reason)
            return
        started = await mining_service.start_dig(db, character, None, _rng)
        await screen_service.set_screen(db, character, "mine")
        await db.commit()

    _schedule_finish(message.peer_id, started.seconds)
    await message.answer(
        mt.dig_started_text(started.seconds), keyboard=kb.digging_keyboard()
    )
