"""Рейд «Тропа Безымянного», этап 1: лабиринт (не бой, реальное время).

Логика - game/raid_trail.py. Здесь клавиатура-карта (5×5 кнопок, цвет -
состояние клетки), шаги, рассылка событий, шаги Безымянного и общий таймер:
не успели - гибнет вся группа. Бой с Безымянным - третьим этапом через
bot/handlers/raid_combat.py (begin_combat_stage). Состояние - в памяти.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot import raid_trail_texts as tt
from bot.keyboards import raid as raid_kb
from game import raid_trail as lab_rules
from game.economy import raid_trail_config as tc

labeler = BotLabeler()
labeler.vbml_ignore_case = True
_rng = random.Random()

_COLOR_ME = KeyboardButtonColor.POSITIVE
_COLOR_SEEN = KeyboardButtonColor.SECONDARY
_COLOR_FOG = KeyboardButtonColor.PRIMARY
_COLOR_DANGER = KeyboardButtonColor.NEGATIVE


@dataclass
class TrailRun:
    battle_id: int
    peers: dict[int, int]        # character_id -> peer_id
    names: dict[int, str]
    numbers: dict[int, int]      # character_id -> номер на карте
    lab: lab_rules.Labyrinth
    token: int = 0
    deadline: float = 0.0
    done: bool = False
    task: asyncio.Task | None = None
    walking: dict[int, asyncio.Task] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_runs: dict[int, TrailRun] = {}
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
        logger.exception("Тропа: не удалось написать {}", peer_id)


def _left(run: TrailRun) -> str:
    seconds = max(0, int(run.deadline - time.monotonic()))
    return f"⏳ {seconds // 60}:{seconds % 60:02d}"


def abort(battle_id: int) -> None:
    run = _runs.pop(battle_id, None)
    if run is None:
        return
    run.done = True
    _stop_walks(run)
    if run.task is not None:
        run.task.cancel()
    for peer in run.peers.values():
        _peer_run.pop(peer, None)


# --- Клавиатура-карта ----------------------------------------------------------------


def _cell_button(run: TrailRun, viewer: int, i: int) -> tuple[str, KeyboardButtonColor]:
    lab = run.lab
    kind = lab.kind(i)
    seen = i in lab.explored
    if lab.pos[viewer] == i:
        return "📍", _COLOR_ME
    if lab.hunter == i and lab.hunter_near(viewer):
        return "👤", _COLOR_DANGER
    others = [run.numbers[c] for c, p in lab.pos.items() if p == i and c != viewer]
    if others:
        return str(min(others)), _COLOR_SEEN
    if i == lab_rules.GATE:
        return "🚪", _COLOR_SEEN if seen else _COLOR_FOG
    if not seen:
        return "·", _COLOR_FOG
    if i == lab_rules.START:
        return "🏁", _COLOR_SEEN
    if kind == lab_rules.PIT:
        return "🕳", _COLOR_DANGER
    if kind == lab_rules.FOOTPRINT and i not in lab.found:
        return "👣", _COLOR_SEEN
    if kind == lab_rules.PLATE:
        return "⚖️", _COLOR_SEEN
    if kind == lab_rules.REST and not lab.rest_used:
        return "🕯", _COLOR_SEEN
    if kind == lab_rules.ECHO:
        return "🧭", _COLOR_SEEN
    return "·", _COLOR_SEEN


def map_keyboard(run: TrailRun, viewer: int) -> str:
    kb = Keyboard(one_time=False)
    for r in range(lab_rules.N):
        for c in range(lab_rules.N):
            i = lab_rules.idx(r, c)
            label, color = _cell_button(run, viewer, i)
            kb.add(Text(label, payload={"type": "trl", "t": run.token, "c": i}), color=color)
        kb.row()
    kb.add(Text(tt.BTN_WHERE, payload={"type": "trl_where", "t": run.token}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def keyboard_for(peer_id: int) -> str | None:
    """/клавиатура и восстановление экрана: карта или ожидание."""
    run = _runs.get(_peer_run.get(peer_id))
    if run is None:
        return raid_kb.raid_waiting_keyboard()
    cid = next((c for c, p in run.peers.items() if p == peer_id), None)
    if cid is None:
        return raid_kb.raid_waiting_keyboard()
    return map_keyboard(run, cid)


# --- Тексты клетки -------------------------------------------------------------------


def _place_key(run: TrailRun, i: int) -> str:
    if i == lab_rules.START:
        return "start"
    if i == lab_rules.GATE:
        return "gate"
    kind = run.lab.kind(i)
    if kind and not (kind == lab_rules.FOOTPRINT and i in run.lab.found):
        return kind
    return run.lab.maze.places[i]


def _place_name(run: TrailRun, i: int) -> str:
    return tt.KIND_NAMES.get(_place_key(run, i)) or run.lab.maze.names[i]


def _status(run: TrailRun) -> str:
    found = len(run.lab.found)
    return f"👣 Следов: {found}/{tc.FOOTPRINTS} · {_left(run)}"


def _cell_text(run: TrailRun, cid: int, header: list[str] | None = None) -> str:
    lab = run.lab
    here = lab.pos[cid]
    key = _place_key(run, here)
    lines = tt.PLACE_LINES.get(key, ("",))
    line = tt.KIND_LINES.get(key) or lines[here % len(lines)]
    name = _place_name(run, here)
    exits = " ".join(lab_rules.DIR_ARROWS[d] for d in lab.exits(here)) or "-"
    parts = list(header or [])
    parts.append(f"📍 {name}\n{line}".rstrip())
    parts.append(f"Выходы: {exits}\n{_status(run)}")
    return "\n\n".join(parts)


async def _show_cell(run: TrailRun, cid: int, header: list[str] | None = None, photo_key: str | None = None) -> None:
    key = photo_key or _place_key(run, run.lab.pos[cid])
    await _send(run.peers[cid], _cell_text(run, cid, header), map_keyboard(run, cid), tt.place_attachment(key))


async def _tell(run: TrailRun, cid: int, text: str, photo_key: str | None = None) -> None:
    """Событие игроку - со свежей картой: его клавиатура иначе устарела бы."""
    await _send(run.peers[cid], f"{text}\n\n{_status(run)}", map_keyboard(run, cid),
                tt.place_attachment(photo_key) if photo_key else None)


# --- Старт ---------------------------------------------------------------------------


async def start(battle_id: int, battle) -> None:
    peers = {cid: p.peer_id for cid, p in battle.participants.items()}
    names = {cid: p.name for cid, p in battle.participants.items()}
    order = sorted(peers)
    now = time.monotonic()
    run = TrailRun(
        battle_id=battle_id, peers=peers, names=names,
        numbers={cid: n for n, cid in enumerate(order, start=1)},
        lab=lab_rules.Labyrinth(order, _rng, now),
        token=next(_tokens), deadline=now + tc.LABYRINTH_SECONDS,
    )
    _runs[battle_id] = run
    for peer in peers.values():
        _peer_run[peer] = battle_id
    intro = tt.STAGE1_TEXT if len(peers) > 1 else tt.SOLO_STAGE1_TEXT
    for cid, peer in peers.items():
        await _send(peer, intro, attachment=tt.stage_attachment(1))
        await _show_cell(run, cid)
    run.task = asyncio.get_running_loop().create_task(_watch(battle_id, run.token))


# --- Шаги ----------------------------------------------------------------------------


def _run_and_cid(message: Message, payload: dict) -> tuple[TrailRun | None, int | None]:
    run = _runs.get(_peer_run.get(message.peer_id))
    if run is None or run.done or payload.get("t") != run.token:
        return None, None
    cid = next((c for c, p in run.peers.items() if p == message.peer_id), None)
    return run, cid


_REFUSALS = {
    "wall": tt.REFUSE_WALL, "grate": tt.REFUSE_GRATE, "not_adjacent": tt.REFUSE_FAR,
    "frozen": tt.REFUSE_FROZEN,
}


@labeler.message(payload_contains={"type": "trl"})
async def on_step(message: Message) -> None:
    payload = message.get_payload_json() or {}
    run, cid = _run_and_cid(message, payload)
    if run is None or cid is None:
        return
    target = payload.get("c")
    if not isinstance(target, int):
        return
    async with run.lock:
        if run.done:
            return
        now = time.monotonic()
        lab = run.lab
        if target == lab.pos[cid]:
            await _show_cell(run, cid)
            return
        if cid in run.walking:
            await _send(message.peer_id, tt.REFUSE_WALKING)
            return
        reason = lab.check(cid, target, now)
        if reason:
            await _send(message.peer_id, _REFUSALS.get(reason, tt.REFUSE_WALL), map_keyboard(run, cid))
            return
        if tc.STEP_SECONDS <= 0:
            await _after_move(run, cid, lab.move(cid, target, now), now)
            return
        # Переход идёт tc.STEP_SECONDS (2026-10-20, владелец): иначе карту
        # пробегают кликами за минуту. Стена и решётка отказывают сразу.
        await _send(message.peer_id, tt.WALKING.format(side=lab_rules.compass(lab.pos[cid], target)))
        run.walking[cid] = asyncio.get_running_loop().create_task(_walk(run, cid, target))


async def _walk(run: TrailRun, cid: int, target: int) -> None:
    try:
        await asyncio.sleep(tc.STEP_SECONDS)
    except asyncio.CancelledError:
        return
    async with run.lock:
        run.walking.pop(cid, None)
        if run.done:
            return
        now = time.monotonic()
        result = run.lab.move(cid, target, now)
        if not result.ok:
            # Пока шёл, поймал Безымянный (уже сказали) или закрылась решётка.
            if result.reason == "grate":
                await _send(run.peers[cid], tt.REFUSE_GRATE, map_keyboard(run, cid))
            return
        await _after_move(run, cid, result, now)


def _stop_walks(run: TrailRun) -> None:
    for task in run.walking.values():
        task.cancel()
    run.walking.clear()


async def _after_move(run: TrailRun, cid: int, result: lab_rules.MoveResult, now: float) -> None:
    lab = run.lab
    header: list[str] = []
    photo = None
    found = len(lab.found)
    place = _place_name(run, lab.pos[cid])
    if "footprint" in result.events:
        header.append(tt.EVENT_FOOTPRINT.format(found=found, total=tc.FOOTPRINTS))
        photo = "footprint"
        for other in run.peers:
            if other != cid:
                await _tell(run, other, tt.EVENT_FOOTPRINT_OTHERS.format(
                    name=run.names[cid], place=place, found=found, total=tc.FOOTPRINTS))
    if "pit" in result.events:
        header.append(tt.EVENT_PIT)
        photo = "pit"
    if "rest" in result.events:
        run.deadline += tc.REST_BONUS_SECONDS
        header.append(tt.EVENT_REST.format(seconds=tc.REST_BONUS_SECONDS))
    if "echo" in result.events:
        header.append(tt.EVENT_ECHO.format(side=result.echo) if result.echo else tt.EVENT_ECHO_NONE)
    if "grate" in result.events:
        for other in run.peers:
            if other != cid:
                await _tell(run, other, tt.EVENT_GRATE, "grate")
        header.append(tt.EVENT_GRATE)
        photo = photo or "grate"
    if "caught" in result.events:
        await _caught(run, [cid])
        return
    if lab.done(now):
        await _show_cell(run, cid, header, photo)
        await _finish(run)
        return
    if lab.pos[cid] == lab_rules.GATE and not lab.footprints_left():
        left = sum(1 for c in run.peers if lab.pos[c] != lab_rules.GATE)
        header.append(tt.AT_GATE_WAIT.format(left=left))
    elif lab.hunter_near(cid):
        header.append(tt.EVENT_NEAR)
    await _show_cell(run, cid, header, photo)


async def _caught(run: TrailRun, cids: list[int]) -> None:
    for cid in cids:
        walk = run.walking.pop(cid, None)
        if walk is not None:
            walk.cancel()
        await _tell(run, cid, tt.EVENT_CAUGHT.format(seconds=round(tc.CAUGHT_SECONDS)), "caught")
        for other in run.peers:
            if other != cid:
                await _tell(run, other, tt.EVENT_CAUGHT_OTHERS.format(name=run.names[cid]))


@labeler.message(payload_contains={"type": "trl_where"})
async def where_all(message: Message) -> None:
    payload = message.get_payload_json() or {}
    run, cid = _run_and_cid(message, payload)
    if run is None or cid is None:
        return
    now = time.monotonic()
    lines = ["📜 Где все:"]
    for other, n in sorted(run.numbers.items(), key=lambda kv: kv[1]):
        where = _place_name(run, run.lab.pos[other])
        mark = " (без имени)" if run.lab.is_frozen(other, now) else ""
        me = " - ты" if other == cid else ""
        lines.append(f"{n}. {run.names[other]}{me}: {where}{mark}")
    await _send(message.peer_id, "\n".join(lines) + f"\n\n{_status(run)}", map_keyboard(run, cid))


# --- Финиш ---------------------------------------------------------------------------


async def _finish(run: TrailRun) -> None:
    from bot.handlers import raid_combat

    run.done = True
    _stop_walks(run)
    if run.task is not None:
        run.task.cancel()
        run.task = None
    _runs.pop(run.battle_id, None)
    for peer in run.peers.values():
        _peer_run.pop(peer, None)
    notices = await raid_combat.award_stage(run.battle_id)
    for cid, peer in run.peers.items():
        notice = notices.get(cid)
        text = tt.STAGE1_DONE_TEXT
        await _send(peer, f"{text}\n\n{notice}" if notice else text, raid_kb.raid_waiting_keyboard())
    await raid_combat.begin_combat_stage(run.battle_id, stage=3)


# --- Таймер и Безымянный ------------------------------------------------------------


async def _watch(battle_id: int, token: int) -> None:
    warned = False
    try:
        while True:
            run = _runs.get(battle_id)
            if run is None or run.done or run.token != token:
                return
            now = time.monotonic()
            left = run.deadline - now
            if left <= 0:
                break
            if not warned and left <= 60:
                warned = True
                for peer in run.peers.values():
                    await _send(peer, tt.MINUTE_LEFT)
            async with run.lock:
                if run.done:
                    return
                await _world_tick(run, now)
            await asyncio.sleep(1.0)
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
        await raid_combat.wipe(battle_id, tt.TIMEOUT_TEXT)
    except Exception:
        logger.exception("Тропа: сбой при гибели группы по таймеру {}", battle_id)


async def _world_tick(run: TrailRun, now: float) -> None:
    lab = run.lab
    for cid in lab.release(now):
        await _show_cell(run, cid, [tt.EVENT_RELEASED])
    lab.update_plates(now)
    near_before = {c for c in run.peers if lab.hunter_near(c)}
    hunted = lab.hunter_tick(now)
    if not hunted.moved:
        return
    if hunted.caught:
        await _caught(run, hunted.caught)
    for cid in hunted.near:
        if cid not in near_before:
            await _tell(run, cid, tt.EVENT_NEAR, "near")
