"""Рейд «Безликий архив», этапы 1-2: головоломки и загадки (не бой).

Этап 1. У каждого своя головоломка (game/raid_puzzles.py), поле - кнопками.
Общий таймер ac.PUZZLE_SECONDS: решившие ждут остальных, не успели все -
гибнет вся группа.

Этап 2. У каждого своя загадка, ответ - слово фразы с известным номером
(game/archive_riddles.py). Ответ пишется сообщением, бот сразу говорит,
верно ли. Лидер собирает слова в общем чате и вводит фразу целиком.
Неверная фраза сжигает ac.WRONG_PHRASE_PENALTY_SECONDS. Таймер
ac.RIDDLE_SECONDS, не успели - гибель группы.

Дальше бой с Архивариусом ведёт bot/handlers/raid_combat.py
(begin_combat_stage). Состояние - в памяти процесса, как у всего рейда.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from bot import raid_archive_texts as at
from bot.keyboards import raid as raid_kb
from game import archive_riddles, raid_puzzles
from game.economy import raid_archive_config as ac

labeler = BotLabeler()
_rng = random.Random()


@dataclass
class ArchiveRun:
    battle_id: int
    peers: dict[int, int]                 # character_id -> peer_id
    names: dict[int, str]
    leader_id: int
    stage: int = 1
    token: int = 0
    deadline: float = 0.0
    puzzles: dict[int, raid_puzzles.Puzzle] = field(default_factory=dict)
    phrase: archive_riddles.Phrase | None = None
    #: character_id -> номера слов (позиции), которые ему загаданы
    riddles: dict[int, list[int]] = field(default_factory=dict)
    solved_words: set[int] = field(default_factory=set)
    done: bool = False
    task: asyncio.Task | None = None
    busy: bool = False


_runs: dict[int, ArchiveRun] = {}
_peer_run: dict[int, int] = {}
_tokens = iter(range(1, 10**9))


def _api():
    from bot.handlers import raid_combat

    return raid_combat._bot_api


async def _send(peer_id: int, text: str, keyboard: str | None = None, attachment: str | None = None) -> None:
    try:
        await _api().messages.send(
            peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, attachment=attachment,
        )
    except Exception:
        logger.exception("Архив: не удалось написать {}", peer_id)


def _left(run: ArchiveRun) -> str:
    seconds = max(0, int(run.deadline - time.monotonic()))
    return f"⏳ {seconds // 60}:{seconds % 60:02d}"


def abort(battle_id: int) -> None:
    run = _runs.pop(battle_id, None)
    if run is None:
        return
    run.done = True
    if run.task is not None:
        run.task.cancel()
    for peer in run.peers.values():
        _peer_run.pop(peer, None)


# --- Старт ------------------------------------------------------------------------


async def start(battle_id: int, battle) -> None:
    peers = {cid: p.peer_id for cid, p in battle.participants.items()}
    names = {cid: p.name for cid, p in battle.participants.items()}
    leader = battle.leader_id if battle.leader_id in peers else min(peers)
    run = ArchiveRun(battle_id=battle_id, peers=peers, names=names, leader_id=leader)
    _runs[battle_id] = run
    for peer in peers.values():
        _peer_run[peer] = battle_id
    await _start_puzzles(run)


async def _start_puzzles(run: ArchiveRun) -> None:
    run.stage = 1
    run.token = next(_tokens)
    run.deadline = time.monotonic() + ac.PUZZLE_SECONDS
    order = sorted(run.peers)
    for cid, puzzle in zip(order, raid_puzzles.deal(_rng, len(order)), strict=True):
        run.puzzles[cid] = puzzle
    intro = at.STAGE1_TEXT if len(run.peers) > 1 else at.SOLO_STAGE1_TEXT
    for cid, peer in run.peers.items():
        await _send(peer, intro, attachment=at.stage_attachment(1))
        await _send_puzzle(run, cid, "")
    run.task = asyncio.get_running_loop().create_task(_watch(run.battle_id, run.token))


def _puzzle_keyboard(run: ArchiveRun, puzzle: raid_puzzles.Puzzle) -> str:
    """Поле головоломки - обычная (не инлайн) клавиатура: у пар 12 кнопок,
    инлайн столько не держит."""
    kb = Keyboard(one_time=False)
    for row in puzzle.cells():
        for label, value in row:
            kb.add(Text(label, payload={"type": "apz", "t": run.token, "v": value}),
                   color=KeyboardButtonColor.SECONDARY)
        kb.row()
    if kb.buttons and not kb.buttons[-1]:
        kb.buttons.pop()
    return kb.get_json()


async def _send_puzzle(run: ArchiveRun, cid: int, event_line: str) -> None:
    puzzle = run.puzzles[cid]
    parts = [puzzle.title]
    if event_line:
        parts.append(event_line)
    else:
        parts.append(puzzle.rules)
    status = puzzle.status()
    if status:
        parts.append(status)
    parts.append(_left(run))
    await _send(run.peers[cid], "\n\n".join(parts), _puzzle_keyboard(run, puzzle))


def keyboard_for(peer_id: int) -> str | None:
    """/клавиатура и восстановление экрана: поле головоломки или ожидание."""
    battle_id = _peer_run.get(peer_id)
    run = _runs.get(battle_id) if battle_id is not None else None
    if run is None:
        return raid_kb.raid_waiting_keyboard()
    cid = next((c for c, p in run.peers.items() if p == peer_id), None)
    puzzle = run.puzzles.get(cid)
    if run.stage == 1 and puzzle is not None and not puzzle.solved:
        return _puzzle_keyboard(run, puzzle)
    return raid_kb.raid_waiting_keyboard()


# --- Нажатия в головоломках -------------------------------------------------------


@labeler.message(payload_contains={"type": "apz"})
async def on_press(message: Message) -> None:
    battle_id = _peer_run.get(message.peer_id)
    run = _runs.get(battle_id) if battle_id is not None else None
    payload = message.get_payload_json() or {}
    if run is None or run.stage != 1 or run.done or payload.get("t") != run.token:
        return
    cid = next((c for c, p in run.peers.items() if p == message.peer_id), None)
    puzzle = run.puzzles.get(cid)
    if puzzle is None or puzzle.solved:
        return
    line = puzzle.press(str(payload.get("v", "")))
    if not puzzle.solved:
        await _send_puzzle(run, cid, line)
        return
    solved = sum(1 for p in run.puzzles.values() if p.solved)
    total = len(run.puzzles)
    await _send(message.peer_id, f"{line}\n\n✅ Замок открыт. Решили: {solved}/{total}.",
                raid_kb.raid_waiting_keyboard())
    for other, peer in run.peers.items():
        if other != cid:
            await _send(peer, f"✅ {run.names[cid]} открыл свой замок ({solved}/{total}).")
    if solved == total:
        await _finish_puzzles(run)


async def _finish_puzzles(run: ArchiveRun) -> None:
    if run.busy or run.done:
        return
    run.busy = True
    try:
        if run.task is not None:
            run.task.cancel()
            run.task = None
        await _reward(run, at.STAGE1_DONE_TEXT)
        await _start_riddles(run)
    finally:
        run.busy = False


async def _reward(run: ArchiveRun, text: str) -> None:
    from bot.handlers import raid_combat

    notices = await raid_combat.award_stage(run.battle_id)
    for cid, peer in run.peers.items():
        notice = notices.get(cid)
        await _send(peer, f"{text}\n\n{notice}" if notice else text, raid_kb.raid_waiting_keyboard())


# --- Загадки ----------------------------------------------------------------------


async def _start_riddles(run: ArchiveRun) -> None:
    from bot.handlers import raid_combat

    battle = raid_combat._battles.get(run.battle_id)
    if battle is not None:
        battle.stage = 2
    run.stage = 2
    run.token = next(_tokens)
    run.deadline = time.monotonic() + ac.RIDDLE_SECONDS
    run.phrase = archive_riddles.deal(_rng, len(run.peers))
    positions = list(range(1, run.phrase.size + 1))
    _rng.shuffle(positions)
    order = sorted(run.peers)
    run.riddles = {cid: [] for cid in order}
    for i, pos in enumerate(positions):
        run.riddles[order[i % len(order)]].append(pos)

    for cid, peer in run.peers.items():
        parts = [at.STAGE2_TEXT]
        for pos in sorted(run.riddles[cid]):
            a = run.phrase.assignments[pos - 1]
            parts.append(f"❓ «{a.question}»\nОтвет - слово №{pos} из {run.phrase.size}.")
        parts.append("Ответ напиши сообщением.")
        if cid == run.leader_id:
            parts.append(
                f"👑 Ты лидер. Когда соберёте слова, введи строку двери целиком:\n{run.phrase.masked()}"
            )
        parts.append(_left(run))
        await _send(peer, "\n\n".join(parts), raid_kb.raid_waiting_keyboard(), at.stage_attachment(2))
    run.task = asyncio.get_running_loop().create_task(_watch(run.battle_id, run.token))


class ArchiveAnswer(ABCRule[Message]):
    """Свободный текст - ответ на загадку или фраза лидера, только пока идёт этап загадок."""

    async def check(self, event: Message) -> bool:
        battle_id = _peer_run.get(event.peer_id)
        run = _runs.get(battle_id) if battle_id is not None else None
        return bool(run and run.stage == 2 and not run.done and event.text and not event.payload)


@labeler.message(ArchiveAnswer())
async def on_answer(message: Message) -> None:
    run = _runs.get(_peer_run.get(message.peer_id))
    if run is None or run.phrase is None or run.done:
        return
    cid = next((c for c, p in run.peers.items() if p == message.peer_id), None)
    if cid is None:
        return
    text = message.text.strip()
    words = text.split()

    mine = [pos for pos in run.riddles.get(cid, []) if pos not in run.solved_words]
    if cid == run.leader_id and len(words) >= 2:
        # Несколько слов от лидера - это строка двери. Исключение - когда
        # строка не сошлась, а в ней есть ответ на его собственную загадку
        # («это тень»): тогда засчитываем загадку и не жжём время.
        own = [pos for pos in mine if archive_riddles.answer_is(text, run.phrase.assignments[pos - 1])]
        if not own or archive_riddles.phrase_is(text, run.phrase):
            await _phrase_attempt(run, text)
            return

    for pos in mine:
        assignment = run.phrase.assignments[pos - 1]
        if archive_riddles.answer_is(text, assignment):
            run.solved_words.add(pos)
            tail = "" if cid == run.leader_id else " Передай его лидеру."
            await message.answer(f"✅ Верно. Слово №{pos}: «{assignment.word}».{tail}")
            return
    if mine:
        await message.answer(f"❌ Не то. {_left(run)}")
    elif cid == run.leader_id:
        await message.answer("Строку двери вводи целиком, все слова сразу.")


async def _phrase_attempt(run: ArchiveRun, text: str) -> None:
    if archive_riddles.phrase_is(text, run.phrase):
        if run.busy or run.done:
            return
        run.busy = True
        try:
            if run.task is not None:
                run.task.cancel()
                run.task = None
            run.stage = 3
            await _reward(run, f"«{run.phrase.full()}»\n\n{at.STAGE2_DONE_TEXT}")
            await _begin_boss(run)
        finally:
            run.busy = False
        return
    run.deadline -= ac.WRONG_PHRASE_PENALTY_SECONDS
    for peer in run.peers.values():
        await _send(
            peer,
            f"🔥 Лидер прочёл строку неверно, и дверь сжигает {ac.WRONG_PHRASE_PENALTY_SECONDS} сек. {_left(run)}",
        )


async def _begin_boss(run: ArchiveRun) -> None:
    from bot.handlers import raid_combat

    _runs.pop(run.battle_id, None)
    for peer in run.peers.values():
        _peer_run.pop(peer, None)
    run.done = True
    await raid_combat.begin_combat_stage(run.battle_id)


# --- Таймер -----------------------------------------------------------------------


async def _watch(battle_id: int, token: int) -> None:
    """Ждёт конца этапа. Дедлайн может сдвигаться (штраф за неверную фразу),
    поэтому сверяемся с ним понемногу, а не спим весь срок разом."""
    warned = False
    try:
        while True:
            run = _runs.get(battle_id)
            if run is None or run.done or run.token != token:
                return
            left = run.deadline - time.monotonic()
            if left <= 0:
                break
            if not warned and left <= 60:
                warned = True
                for peer in run.peers.values():
                    await _send(peer, "⏳ Осталась минута.")
            await asyncio.sleep(min(left, 5))
    except asyncio.CancelledError:
        return
    run = _runs.get(battle_id)
    if run is None or run.done or run.token != token or run.busy:
        return
    run.done = True
    from bot.handlers import raid_combat

    abort(battle_id)
    try:
        await raid_combat.wipe(battle_id, at.TIMEOUT_TEXT)
    except Exception:
        logger.exception("Архив: сбой при гибели группы по таймеру {}", battle_id)
