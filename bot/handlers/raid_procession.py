"""Рейд «Жернова Паломников», этап 1: шествие (не бой).

Логика ритма - game/raid_procession.py. Здесь рассылка ударов, кнопки шагов
и общий таймер mc.PROCESSION_SECONDS: не дошли - гибнет вся группа. Дальше
обоз и Мельник идут боем через bot/handlers/raid_combat.py
(begin_combat_stage). Состояние - в памяти процесса, как у всего рейда.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot import raid_mill_texts as mt
from bot.keyboards import raid as raid_kb
from game import raid_procession as rp
from game.economy import raid_mill_config as mc

labeler = BotLabeler()
labeler.vbml_ignore_case = True
_rng = random.Random()

_BUTTONS = ((rp.LEFT, mt.BTN_LEFT), (rp.RIGHT, mt.BTN_RIGHT), (rp.HOLD, mt.BTN_HOLD))


@dataclass
class ProcessionRun:
    battle_id: int
    peers: dict[int, int]       # character_id -> peer_id
    names: dict[int, str]
    procession: rp.Procession
    token: int = 0
    deadline: float = 0.0
    done: bool = False
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_runs: dict[int, ProcessionRun] = {}
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
        logger.exception("Шествие: не удалось написать {}", peer_id)


def _left(run: ProcessionRun) -> str:
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


def _step_keyboard(run: ProcessionRun) -> str:
    kb = Keyboard(one_time=False)
    beat = run.procession.beat
    for move, label in _BUTTONS:
        kb.add(Text(label, payload={"type": "mpr", "t": run.token, "b": beat, "m": move}),
               color=KeyboardButtonColor.PRIMARY if move != rp.HOLD else KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def keyboard_for(peer_id: int) -> str | None:
    """/клавиатура и восстановление экрана: шаги или ожидание."""
    run = _runs.get(_peer_run.get(peer_id))
    if run is None:
        return raid_kb.raid_waiting_keyboard()
    cid = next((c for c, p in run.peers.items() if p == peer_id), None)
    if cid is None or cid in run.procession.moves:
        return raid_kb.raid_waiting_keyboard()
    return _step_keyboard(run)


def _beat_text(run: ProcessionRun, cid: int, header: str = "") -> str:
    proc = run.procession
    parts = [header] if header else []
    parts.append(f"🥁 Удар {proc.position + 1} из {mc.BAR_BEATS}\nРитм: {proc.rhythm_line(cid)}")
    parts.append(
        f"👣 Шагов: {proc.steps}/{mc.STEPS_REQUIRED} · 🩼 хромота: {proc.lame.get(cid, 0)}/{mc.LAME_LIMIT}"
    )
    parts.append(_left(run))
    return "\n\n".join(parts)


async def _send_beat(run: ProcessionRun, header: str = "") -> None:
    keyboard = _step_keyboard(run)
    for cid, peer in run.peers.items():
        await _send(peer, _beat_text(run, cid, header), keyboard)


# --- Старт ------------------------------------------------------------------------


async def start(battle_id: int, battle) -> None:
    peers = {cid: p.peer_id for cid, p in battle.participants.items()}
    names = {cid: p.name for cid, p in battle.participants.items()}
    run = ProcessionRun(
        battle_id=battle_id, peers=peers, names=names,
        procession=rp.Procession(players=sorted(peers), rng=_rng),
        token=next(_tokens), deadline=time.monotonic() + mc.PROCESSION_SECONDS,
    )
    _runs[battle_id] = run
    for peer in peers.values():
        _peer_run[peer] = battle_id
    intro = mt.STAGE1_TEXT if len(peers) > 1 else mt.SOLO_STAGE1_TEXT
    for peer in peers.values():
        await _send(peer, intro, attachment=mt.stage_attachment(1))
    await _send_beat(run)
    run.task = asyncio.get_running_loop().create_task(_watch(battle_id, run.token))


# --- Шаги -------------------------------------------------------------------------


@labeler.message(payload_contains={"type": "mpr"})
async def on_step(message: Message) -> None:
    run = _runs.get(_peer_run.get(message.peer_id))
    payload = message.get_payload_json() or {}
    if run is None or run.done or payload.get("t") != run.token:
        return
    cid = next((c for c, p in run.peers.items() if p == message.peer_id), None)
    if cid is None:
        return
    async with run.lock:
        proc = run.procession
        if run.done or payload.get("b") != proc.beat:
            return
        if not proc.press(cid, str(payload.get("m", ""))):
            return
        if not proc.ready:
            waiting = len(proc.players) - len(proc.moves)
            await _send(message.peer_id, f"👣 Шаг выбран. Ждём остальных: {waiting}.",
                        raid_kb.raid_waiting_keyboard())
            return
        await _resolve(run)


async def _resolve(run: ProcessionRun) -> None:
    proc = run.procession
    result = proc.resolve()
    lines = []
    if result.stepped:
        lines.append(f"👣 Шаг в такт. {proc.steps}/{mc.STEPS_REQUIRED}")
    else:
        lines.append("❌ Сбились с шага: " + ", ".join(run.names[c] for c in result.wrong))
    for cid in result.fallen:
        lines.append(
            f"🩼 {run.names[cid]} падает, колонна ждёт: -{mc.LAG_STEPS_LOST} шага. Хромота с него сошла."
        )
    if result.new_pattern:
        lines.append("🥁 Барабан меняет ритм.")
    header = "\n".join(lines)
    if proc.done:
        await _finish(run, header)
        return
    await _send_beat(run, header)


async def _finish(run: ProcessionRun, header: str) -> None:
    from bot.handlers import raid_combat

    run.done = True
    if run.task is not None:
        run.task.cancel()
        run.task = None
    _runs.pop(run.battle_id, None)
    for peer in run.peers.values():
        _peer_run.pop(peer, None)
    notices = await raid_combat.award_stage(run.battle_id)
    for cid, peer in run.peers.items():
        notice = notices.get(cid)
        text = f"{header}\n\n{mt.STAGE1_DONE_TEXT}"
        await _send(peer, f"{text}\n\n{notice}" if notice else text, raid_kb.raid_waiting_keyboard())
    await raid_combat.begin_combat_stage(run.battle_id, stage=2, lame=dict(run.procession.lame))


# --- Таймер -----------------------------------------------------------------------


async def _watch(battle_id: int, token: int) -> None:
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
                    await _send(peer, "⏳ Осталась минута. Жёрнов уже в сотне шагов.")
            await asyncio.sleep(min(left, 5))
    except asyncio.CancelledError:
        return
    run = _runs.get(battle_id)
    if run is None or run.done or run.token != token:
        return
    run.done = True
    from bot.handlers import raid_combat

    run.task = None
    abort(battle_id)
    try:
        await raid_combat.wipe(battle_id, mt.TIMEOUT_TEXT)
    except Exception:
        logger.exception("Шествие: сбой при гибели группы по таймеру {}", battle_id)
