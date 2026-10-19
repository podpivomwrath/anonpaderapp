"""Арена (2026-10-18, решение владельца): тренировочные бои игроков в городе.

Вход - из Таверны. Три способа найти соперника:
- «Случайный бой» - очередь: первый ждёт, второй нажавший сразу дерётся с ним;
- «Ждать соперника» - игрок получает код и ждёт, пока его не введут;
- «Найти соперника» - игрок вводит чужой код, и бой начинается.

Бой - обычная дуэль (bot/handlers/pvp.py, Battle.arena), но без смерти,
трофеев, рейтинга и эликсиров; оба начинают с полным здоровьем. После боя,
каким бы ни был итог, оба возвращаются на экран арены.

Очереди и коды - в памяти процесса: рестарт их сбрасывает, и это не страшно
(игрок просто нажмёт кнопку ещё раз).
"""

import random

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from bot.dispatch_rules import is_slash_command
from bot.keyboards import arena as arena_kb
from bot.keyboards.world import BTN_ARENA
from bot.vk_media import photo_attachment
from bot.world_texts import FOREIGN_NPC_REJECTION
from game.world import grid
from models import Character
from services import screen_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True

SCREEN = "arena"
ARENA_PHOTO_ID = "457239248"
CODE_DIGITS = 4

_rng = random.Random()
_bot_api = None
#: Очередь случайного боя: [(character_id, peer_id)], первый - дольше всех ждёт.
_random_queue: list[tuple[int, int]] = []
#: Код ожидания -> (character_id, peer_id).
_codes: dict[str, tuple[int, int]] = {}
#: Кто сейчас вводит чужой код.
_entering: set[int] = set()

ARENA_TEXT = (
    "🏟 Арена. Здесь бьются ради опыта, а не ради добычи: никто не умирает и "
    "ничего не теряет, эликсиры не тратятся, оба выходят с полным здоровьем.\n\n"
    "🎲 Случайный бой - сразиться с первым, кто тоже ищет бой.\n"
    "⏳ Ждать соперника - получить код и ждать, пока его введут.\n"
    "🔎 Найти соперника - ввести код того, кто ждёт."
)


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api
    from bot.handlers import pvp

    pvp.on_arena_finished = on_arena_finished


def is_waiting(peer_id: int) -> bool:
    return (
        any(p == peer_id for _, p in _random_queue)
        or any(p == peer_id for _, p in _codes.values())
        or peer_id in _entering
    )


def keyboard_for(peer_id: int) -> str:
    return arena_kb.arena_waiting_keyboard() if is_waiting(peer_id) else arena_kb.arena_keyboard()


def _leave_all(peer_id: int) -> None:
    _random_queue[:] = [e for e in _random_queue if e[1] != peer_id]
    for code in [c for c, (_, p) in _codes.items() if p == peer_id]:
        _codes.pop(code, None)
    _entering.discard(peer_id)


def _code_of(peer_id: int) -> str | None:
    return next((c for c, (_, p) in _codes.items() if p == peer_id), None)


async def _ready(db, character_id: int, peer_id: int):
    """Персонаж, если он может начать бой на арене прямо сейчас, иначе None."""
    from bot.activity import blocked_reason

    character = await db.get(Character, character_id)
    if character is None or grid.city_region_at(character.pos_x, character.pos_y) is None:
        return None
    if character.screen != SCREEN or await blocked_reason(db, character, peer_id):
        return None
    return character


async def _arena_character(message: Message):
    """Свой персонаж на экране арены, иначе None (чужие кнопки молчат)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.peer_id)
        if character is None or character.screen != SCREEN:
            return None
        return character


@labeler.message(text=[BTN_ARENA])
async def open_arena(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.peer_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return
        if region != character.region:
            await message.answer(FOREIGN_NPC_REJECTION)
            return
        await screen_service.set_screen(db, character, SCREEN)
        await db.commit()
    await message.answer(ARENA_TEXT, attachment=photo_attachment(ARENA_PHOTO_ID), keyboard=keyboard_for(message.peer_id))


@labeler.message(text=[arena_kb.BTN_ARENA_BACK])
async def back_to_tavern(message: Message) -> None:
    from bot.handlers import world as world_handlers

    _leave_all(message.peer_id)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.peer_id)
        if character is None or character.screen != SCREEN:
            return
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
        rendered = await world_handlers._render_city_screen(db, character, "tavern")
    if rendered is not None:
        await message.answer(rendered[0], keyboard=rendered[1])


@labeler.message(text=[arena_kb.BTN_ARENA_CANCEL])
async def cancel_wait(message: Message) -> None:
    if await _arena_character(message) is None:
        return
    _leave_all(message.peer_id)
    await message.answer("Ожидание отменено.", keyboard=arena_kb.arena_keyboard())


@labeler.message(text=[arena_kb.BTN_ARENA_RANDOM])
async def random_fight(message: Message) -> None:
    peer_id = message.peer_id
    character = await _arena_character(message)
    if character is None:
        return
    if is_waiting(peer_id):
        await message.answer("Ты уже ждёшь соперника.", keyboard=arena_kb.arena_waiting_keyboard())
        return
    async with get_session_factory()() as db:
        me = await _ready(db, character.id, peer_id)
        if me is None:
            await message.answer("Сейчас на арену не выйти: закончи текущие дела.")
            return
        # Соперник снимается из очереди ДО любого ожидания: два одновременных
        # нажатия не заберут одного и того же.
        while _random_queue:
            cid, peer = _random_queue.pop(0)
            if peer == peer_id:
                continue
            rival = await _ready(db, cid, peer)
            if rival is None:
                continue
            _leave_all(peer)
            await _start(db, rival, peer, me, peer_id)
            return
        _random_queue.append((character.id, peer_id))
    await message.answer(
        "🎲 Ищем соперника. Бой начнётся, как только кто-то ещё нажмёт «Случайный бой».",
        keyboard=arena_kb.arena_waiting_keyboard(),
    )


@labeler.message(text=[arena_kb.BTN_ARENA_HOST])
async def host_fight(message: Message) -> None:
    peer_id = message.peer_id
    character = await _arena_character(message)
    if character is None:
        return
    code = _code_of(peer_id)
    if code is None:
        if is_waiting(peer_id):
            await message.answer("Ты уже ждёшь соперника.", keyboard=arena_kb.arena_waiting_keyboard())
            return
        while code is None or code in _codes:
            code = "".join(_rng.choice("0123456789") for _ in range(CODE_DIGITS))
        _codes[code] = (character.id, peer_id)
    await message.answer(
        f"⏳ Твой код: {code}\n\nПередай его сопернику: он нажимает «Найти соперника» на арене и вводит код. "
        "Пока не отменишь, код ждёт.",
        keyboard=arena_kb.arena_waiting_keyboard(),
    )


@labeler.message(text=[arena_kb.BTN_ARENA_FIND])
async def find_fight(message: Message) -> None:
    peer_id = message.peer_id
    if await _arena_character(message) is None:
        return
    if is_waiting(peer_id) and peer_id not in _entering:
        await message.answer("Ты уже ждёшь соперника.", keyboard=arena_kb.arena_waiting_keyboard())
        return
    _entering.add(peer_id)
    await message.answer("🔎 Введи код соперника.", keyboard=arena_kb.arena_waiting_keyboard())


class CodeInput(ABCRule[Message]):
    """Свободный текст - это код, только пока игрок его вводит."""

    async def check(self, event: Message) -> bool:
        return bool(event.peer_id in _entering and event.text and not event.payload
                    and not is_slash_command(event))


@labeler.message(CodeInput())
async def code_input(message: Message) -> None:
    peer_id = message.peer_id
    character = await _arena_character(message)
    if character is None:
        _entering.discard(peer_id)
        return
    code = (message.text or "").strip()
    host = _codes.get(code)
    if host is None:
        await message.answer("Такого кода нет. Проверь цифры или отмени.", keyboard=arena_kb.arena_waiting_keyboard())
        return
    if host[1] == peer_id:
        await message.answer("Это твой собственный код.", keyboard=arena_kb.arena_waiting_keyboard())
        return
    _codes.pop(code, None)  # до ожидания: код не достанется двоим
    async with get_session_factory()() as db:
        me = await _ready(db, character.id, peer_id)
        rival = await _ready(db, host[0], host[1])
        if me is None:
            _codes[code] = host
            _entering.discard(peer_id)
            await message.answer("Сейчас на арену не выйти: закончи текущие дела.", keyboard=arena_kb.arena_keyboard())
            return
        if rival is None:
            _leave_all(host[1])
            await message.answer("Соперник с этим кодом сейчас не может драться.", keyboard=arena_kb.arena_waiting_keyboard())
            return
        _leave_all(peer_id)
        _leave_all(host[1])
        await _start(db, rival, host[1], me, peer_id)


async def _start(db, first, first_peer: int, second, second_peer: int) -> None:
    from bot.handlers import pvp

    # Вошли в бой - ни кодов, ни очередей за обоими не остаётся: код
    # одноразовый, и вводить его после начала боя бессмысленно.
    _leave_all(first_peer)
    _leave_all(second_peer)
    await pvp.start_arena_duel(db, first, first_peer, second, second_peer)


async def on_arena_finished(battle, result) -> None:
    """Итог боя арены: только сообщение, и оба снова на арене."""
    winner = battle.participants.get(result.winner_id) if result.winner_id is not None else None
    for cid, p in battle.participants.items():
        if result.draw or winner is None:
            text = "🤝 Ничья на арене."
        elif cid == winner.character_id:
            loser = next(o for o in battle.participants.values() if o.character_id != cid)
            text = f"🏆 Победа на арене над {loser.name}!"
        else:
            text = f"🏟 Поражение на арене: {winner.name} сильнее в этот раз."
        text += " Ничего не потеряно - бой тренировочный.\n\nВыбирай следующий бой или возвращайся в таверну."
        await _bot_api.messages.send(peer_id=p.peer_id, message=text, random_id=0, keyboard=arena_kb.arena_keyboard())
