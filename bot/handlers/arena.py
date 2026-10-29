"""Арена (2026-10-18, решение владельца): тренировочные бои игроков в городе.

Вход - из Таверны. Три способа найти соперника:
- «Случайный бой» - очередь: первый ждёт, второй нажавший сразу дерётся с ним;
- «Ждать соперника» - игрок получает код и ждёт, пока его не введут;
- «Найти по коду» - игрок вводит чужой код, и бой начинается.

Комната (2026-10-29, владелец): «Комната на бой» даёт код, остальные входят
по нему через «Найти по коду», каждый выбирает сторону, хозяин начинает
массовый бой. После боя комната остаётся - можно сразу ещё раз.

Бой - обычный бой 1×1 (bot/handlers/pvp.py, Battle.arena), но без смерти,
трофеев, рейтинга и эликсиров; оба начинают с полным здоровьем. После боя,
каким бы ни был итог, оба возвращаются на экран арены.

Очереди и коды - в памяти процесса: рестарт их сбрасывает, и это не страшно
(игрок просто нажмёт кнопку ещё раз).
"""

import random
from dataclasses import dataclass, field

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from bot.dispatch_rules import is_slash_command
from bot.keyboards import arena as arena_kb
from bot.keyboards.world import BTN_ARENA
from bot.vk_media import photo_attachment
from bot.world_texts import FOREIGN_NPC_REJECTION
from game.economy import prerelease_config
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

#: Игроков в комнате, не больше.
ROOM_MAX = 10


@dataclass
class Room:
    code: str
    host_peer: int
    #: peer -> (character_id, имя, сторона 0/1), в порядке входа.
    members: dict[int, tuple[int, str, int]] = field(default_factory=dict)
    fighting: bool = False


#: Комнаты по коду и в какой комнате игрок.
_rooms: dict[str, Room] = {}
_room_of: dict[int, str] = {}


def _arena_text() -> str:
    elixirs = ("зелья, эликсиры и свитки выдаются на бой бесплатно (🌱 Дар первопроходцев)"
               if prerelease_config.arena_free_elixirs() else "эликсиры не тратятся")
    return (
        "🏟 Арена. Здесь бьются ради опыта, а не ради добычи: никто не умирает и "
        f"ничего не теряет, {elixirs}, все выходят с полным здоровьем.\n\n"
        "🎲 Случайный бой - сразиться с первым, кто тоже ищет бой.\n"
        "⏳ Ждать соперника - получить код и ждать, пока его введут.\n"
        "👥 Комната на бой - код для нескольких игроков, стороны выбирают сами, начинаешь ты.\n"
        "🔎 Найти по коду - ввести код соперника или комнаты."
    )


ARENA_TEXT = _arena_text()


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api
    from bot.handlers import pvp

    pvp.on_arena_finished = on_arena_finished


def is_waiting(peer_id: int) -> bool:
    return (
        peer_id in _room_of
        or any(p == peer_id for _, p in _random_queue)
        or any(p == peer_id for _, p in _codes.values())
        or peer_id in _entering
    )


def keyboard_for(peer_id: int) -> str:
    room = _room_for(peer_id)
    if room is not None:
        return arena_kb.room_keyboard(room.host_peer == peer_id)
    return arena_kb.arena_waiting_keyboard() if is_waiting(peer_id) else arena_kb.arena_keyboard()


def keyboard_for_character(character_id: int) -> str:
    """Клавиатура арены при восстановлении экрана: peer там не известен,
    ищем игрока в комнатах по персонажу."""
    for room in _rooms.values():
        for peer, (cid, _, _) in room.members.items():
            if cid == character_id:
                return keyboard_for(peer)
    return arena_kb.arena_keyboard()


def _room_for(peer_id: int) -> Room | None:
    code = _room_of.get(peer_id)
    return _rooms.get(code) if code is not None else None


def _leave_all(peer_id: int) -> None:
    _leave_room(peer_id)
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
    await message.answer(_arena_text(), attachment=photo_attachment(ARENA_PHOTO_ID), keyboard=keyboard_for(message.peer_id))


@labeler.message(text=[arena_kb.BTN_ARENA_BACK])
async def back_to_tavern(message: Message) -> None:
    from bot.handlers import world as world_handlers

    await _leave_and_tell(message.peer_id)
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


@labeler.message(text=[arena_kb.BTN_ARENA_FIND, arena_kb.BTN_ARENA_FIND_OLD])
async def find_fight(message: Message) -> None:
    peer_id = message.peer_id
    if await _arena_character(message) is None:
        return
    if is_waiting(peer_id) and peer_id not in _entering:
        await message.answer("Ты уже ждёшь соперника.", keyboard=arena_kb.arena_waiting_keyboard())
        return
    _entering.add(peer_id)
    await message.answer("🔎 Введи код соперника или комнаты.", keyboard=arena_kb.arena_waiting_keyboard())


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
    if code in _rooms:
        _entering.discard(peer_id)
        await _join_room(message, character, _rooms[code])
        return
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


async def on_arena_finished(battle, winner_id: int | None, draw: bool = False) -> None:
    """Итог боя арены: только сообщение, и оба снова на арене. winner_id
    None - ничья."""
    if battle.arena_room:
        await _room_finished(battle, _rooms.get(battle.arena_room), draw)
        return
    winner = battle.participants.get(winner_id) if winner_id is not None else None
    for cid, p in battle.participants.items():
        if winner is None:
            text = "🤝 Ничья на арене."
        elif cid == winner.character_id:
            loser = next(o for o in battle.participants.values() if o.character_id != cid)
            text = f"🏆 Победа на арене над {loser.name}!"
        else:
            text = f"🏟 Поражение на арене: {winner.name} сильнее в этот раз."
        text += " Ничего не потеряно - бой тренировочный.\n\nВыбирай следующий бой или возвращайся в таверну."
        await _bot_api.messages.send(peer_id=p.peer_id, message=text, random_id=0, keyboard=arena_kb.arena_keyboard())


# --- Комната массового боя (2026-10-29, владелец) ---


def _leave_room(peer_id: int) -> Room | None:
    """Убрать игрока из комнаты. Ушёл хозяин - комната распущена; вернуть
    её, чтобы позвавший разослал новости."""
    code = _room_of.pop(peer_id, None)
    room = _rooms.get(code) if code is not None else None
    if room is None:
        return None
    room.members.pop(peer_id, None)
    if room.host_peer == peer_id or not room.members:
        _rooms.pop(room.code, None)
        for peer in list(room.members):
            _room_of.pop(peer, None)
    return room


def _room_text(room: Room) -> str:
    host = room.members.get(room.host_peer)
    sides = []
    for side, title in ((0, "🔴 Сторона 1"), (1, "🔵 Сторона 2")):
        names = [name for _, name, s in room.members.values() if s == side]
        sides.append(f"{title}: {', '.join(names) if names else 'пусто'}")
    head = f"👥 Комната {room.code}, хозяин - {host[1] if host else '?'}. Игроков {len(room.members)} из {ROOM_MAX}."
    return f"{head}\n" + "\n".join(sides) + "\n\nКод передай тем, кого зовёшь: «Найти по коду» на арене. Бой начинает хозяин."


async def _tell_room(room: Room, text: str, skip: int | None = None) -> None:
    for peer in list(room.members):
        if peer == skip:
            continue
        try:
            await _bot_api.messages.send(
                peer_id=peer, message=text, random_id=0, keyboard=arena_kb.room_keyboard(peer == room.host_peer),
            )
        except Exception:
            pass


async def _tell_disbanded(room: Room, text: str) -> None:
    for peer in list(room.members):
        try:
            await _bot_api.messages.send(peer_id=peer, message=text, random_id=0, keyboard=arena_kb.arena_keyboard())
        except Exception:
            pass


async def _leave_and_tell(peer_id: int) -> None:
    room = _room_for(peer_id)
    if room is None:
        return
    name = room.members.get(peer_id, (0, "?", 0))[1]
    was_host = room.host_peer == peer_id
    _leave_room(peer_id)
    if was_host:
        await _tell_disbanded(room, f"👥 {name} распускает комнату {room.code}.")
    elif room.code in _rooms:
        await _tell_room(room, f"{name} выходит из комнаты.\n\n{_room_text(room)}")


@labeler.message(text=[arena_kb.BTN_ROOM_CREATE])
async def create_room(message: Message) -> None:
    peer_id = message.peer_id
    character = await _arena_character(message)
    if character is None:
        return
    if is_waiting(peer_id):
        await message.answer("Ты уже ждёшь боя.", keyboard=keyboard_for(peer_id))
        return
    code = None
    while code is None or code in _codes or code in _rooms:
        code = "".join(_rng.choice("0123456789") for _ in range(CODE_DIGITS))
    room = Room(code=code, host_peer=peer_id)
    room.members[peer_id] = (character.id, character.name, 0)
    _rooms[code] = room
    _room_of[peer_id] = code
    await message.answer(_room_text(room), keyboard=keyboard_for(peer_id))


async def _join_room(message: Message, character, room: Room) -> None:
    peer_id = message.peer_id
    if peer_id in room.members:
        await message.answer(_room_text(room), keyboard=keyboard_for(peer_id))
        return
    if len(room.members) >= ROOM_MAX:
        await message.answer(f"В комнате уже {ROOM_MAX} игроков.", keyboard=arena_kb.arena_keyboard())
        return
    _leave_all(peer_id)
    # Новичок встаёт туда, где меньше народу.
    count = [sum(1 for _, _, s in room.members.values() if s == side) for side in (0, 1)]
    side = 1 if count[1] < count[0] else 0
    room.members[peer_id] = (character.id, character.name, side)
    _room_of[peer_id] = room.code
    note = " Бой уже идёт - войдёшь в следующий." if room.fighting else ""
    await _tell_room(room, f"{character.name} входит в комнату.{note}\n\n{_room_text(room)}")


@labeler.message(text=[arena_kb.BTN_ROOM_SIDE_1, arena_kb.BTN_ROOM_SIDE_2])
async def pick_side(message: Message) -> None:
    peer_id = message.peer_id
    room = _room_for(peer_id)
    if room is None or await _arena_character(message) is None:
        return
    side = 0 if message.text == arena_kb.BTN_ROOM_SIDE_1 else 1
    cid, name, old = room.members[peer_id]
    if old == side:
        await message.answer(_room_text(room), keyboard=keyboard_for(peer_id))
        return
    room.members[peer_id] = (cid, name, side)
    await _tell_room(room, f"{name} переходит на сторону {side + 1}.\n\n{_room_text(room)}")


@labeler.message(text=[arena_kb.BTN_ROOM_LEAVE])
async def leave_room(message: Message) -> None:
    peer_id = message.peer_id
    if _room_for(peer_id) is None or await _arena_character(message) is None:
        return
    await _leave_and_tell(peer_id)
    await message.answer("Ты больше не в комнате.", keyboard=arena_kb.arena_keyboard())


@labeler.message(text=[arena_kb.BTN_ROOM_START])
async def start_room(message: Message) -> None:
    from bot.handlers import pvp

    peer_id = message.peer_id
    room = _room_for(peer_id)
    if room is None or room.host_peer != peer_id or await _arena_character(message) is None:
        return
    if room.fighting:
        await message.answer("Бой этой комнаты ещё идёт.", keyboard=keyboard_for(peer_id))
        return
    async with get_session_factory()() as db:
        roster, absent = [], []
        for peer, (cid, name, side) in list(room.members.items()):
            character = await _ready(db, cid, peer)
            if character is None:
                absent.append(name)
            else:
                roster.append((character, peer, side))
        if {s for _, _, s in roster} != {0, 1}:
            text = "Для боя нужен хотя бы один готовый игрок на каждой стороне."
            if absent:
                text += f" Сейчас заняты или ушли с арены: {', '.join(absent)}."
            await message.answer(text, keyboard=keyboard_for(peer_id))
            return
        room.fighting = True
        await pvp.start_arena_room(db, roster, room.code)
    if absent:
        await _tell_room(room, f"Без боя остались (заняты или ушли с арены): {', '.join(absent)}.")


async def _room_finished(battle, room: Room | None, draw: bool) -> None:
    """Итог боя комнаты: сторона-победитель, все снова в комнате."""
    if room is not None:
        room.fighting = False
    alive = {battle.side_of.get(cid) for cid, c in battle.last_combatants.items()
             if cid in battle.participants and c.alive}
    if draw or len(alive) != 1:
        text = "🤝 Ничья на арене."
    else:
        side = alive.pop()
        names = ", ".join(p.name for cid, p in battle.participants.items() if battle.side_of.get(cid) == side)
        text = f"🏆 Победила сторона {side + 1}: {names}."
    text += " Ничего не потеряно - бой тренировочный."
    for p in battle.participants.values():
        in_room = room is not None and _room_of.get(p.peer_id) == room.code
        tail = "\n\nХозяин может начать бой ещё раз." if in_room else ""
        keyboard = keyboard_for(p.peer_id)
        try:
            await _bot_api.messages.send(peer_id=p.peer_id, message=text + tail, random_id=0, keyboard=keyboard)
        except Exception:
            pass
