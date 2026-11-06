"""Руины культа в чате (2026-11-05): предложение на клетке забоя, вход
группой, ходьба по этажу (направление выбирает лидер, остальные
подтверждают, через минуту группа идёт и так), бой комнаты, мешок, выход
после хозяина этажа, /кик голосованием.

Забег - в базе (services/ruins_service.py), бой комнаты - через
bot/handlers/raid_combat.py (start_ruins_room), его итог возвращается сюда
(on_room_won / on_wipe). Пока игрок в руинах и не в бою, его сообщения
перехватывает этот модуль (стоит в LABELERS рядом с разломами).
"""

from __future__ import annotations

import random
import re

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import FuncRule

from bot import ruins_texts as texts
from bot.activity import activity_action, blocked_reason
from bot.battle_keyboard import in_any_battle
from bot.dispatch_rules import is_info_command
from bot.keyboards.world import add_miniapp_button
from bot.vk_media import photo_attachment
from game import ruins as rules
from game.combat.ruins import RoomStage
from game.economy import ruins_config as rc
from models import Character, RuinRun
from services import group_service, pvp_shield, ruins_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True
_bot_api = None
_rng = random.Random()
#: peer_id -> id забега, пока игрок внутри. Восстанавливается из базы при
#: старте (recover_on_start), снимается выходом, гибелью и изгнанием.
_inside: dict[int, int] = {}


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def is_inside(peer_id: int) -> bool:
    return peer_id in _inside


async def _send(peer_id: int, text: str, keyboard: str | None = None, **kw) -> None:
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, **kw)
    except Exception:
        logger.exception("Руины: не доставлено {}", peer_id)


def _pic(key: str | None) -> str | None:
    """Вложение-картинка руин по ключу ruins_config.PHOTOS (нет номера - None)."""
    photo_id = rc.photo(key)
    return photo_attachment(photo_id) if photo_id else None


def _fight_photo(stage, kind: str, layout: dict) -> str | None:
    """Ключ картинки боя: босс зала, мимик, засада или мобы этажа."""
    from game.combat.ruins import BossRoom

    if isinstance(stage, BossRoom):
        return rc.BOSS_PHOTO_KEYS.get(stage.bosses[0].key) if stage.bosses else None
    if kind == rules.TREASURE:
        return rc.ROOM_PHOTO_KEYS["mimic"]
    if kind == rules.AMBUSH:
        return rc.ROOM_PHOTO_KEYS[rules.AMBUSH]
    mob = rc.MOB_PHOTO_KEYS[int(layout.get("mobs", 0)) % len(rc.MOB_PHOTO_KEYS)]
    return f"{mob}_элита" if kind in (rules.ELITE, rules.BOSS) else mob


def _room_photo(run) -> str | None:
    """Ключ картинки особой комнаты, пока в ней есть выбор."""
    if not ruins_service.room_open(run):
        return None
    kind = rules.room_kind(run.layout, run.pos)
    if kind == rules.EVENT:
        return rc.EVENT_PHOTO_KEYS.get(rules.event_of(run.layout, run.pos) or "")
    return rc.ROOM_PHOTO_KEYS.get(kind)


async def _peers(db, character_ids: list[int]) -> dict[int, int]:
    peers = {}
    for cid in character_ids:
        peer = await onboarding_svc.vk_id_for_character(db, cid)
        if peer is not None:
            peers[cid] = peer
    return peers


# --- Клавиатуры -------------------------------------------------------------------


def _room_keyboard(run, cid: int) -> str:
    """Клавиатура вне боя. Не больше 5 рядов (память vk-keyboard-limits)."""
    from game import ruins_gifts, ruins_rooms

    rows: list[list[tuple[str, dict, KeyboardButtonColor]]] = []
    leader = run.leader_id == cid
    if run.offer:
        if leader:
            for gift_id in run.offer.get("ids", []):
                rows.append([(ruins_gifts.title(gift_id)[:40], {"type": "ruins_gift", "g": gift_id},
                              KeyboardButtonColor.POSITIVE)])
    elif run.phase in (ruins_service.WALK, ruins_service.CLEARED):
        if run.pending:
            if cid not in run.pending.get("ok", []):
                rows.append([(texts.BTN_GO, {"type": "ruins_go"}, KeyboardButtonColor.POSITIVE)])
        elif leader:
            choice_rows = []
            kind = rules.room_kind(run.layout, run.pos)
            if run.phase == ruins_service.CLEARED:
                choice_rows = [[(texts.BTN_DEEPER, {"type": "ruins_deeper"}, KeyboardButtonColor.NEGATIVE),
                                (texts.BTN_UP, {"type": "ruins_up"}, KeyboardButtonColor.POSITIVE)]]
            elif ruins_service.room_open(run):
                if kind == rules.WELL:
                    owned = ruins_gifts.ids(run.gifts)[-4:]
                    buttons = [(f"🔁 {ruins_gifts.BY_ID[g].name}"[:40], {"type": "ruins_room", "c": f"drop:{g}"},
                                KeyboardButtonColor.PRIMARY) for g in owned]
                    choice_rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
                    choice_rows.append([(texts.CHOICE_LABEL["leave"], {"type": "ruins_room", "c": "leave"},
                                         KeyboardButtonColor.SECONDARY)])
                else:
                    options = ruins_rooms.choices(kind, rules.event_of(run.layout, run.pos))
                    choice_rows = [[(texts.CHOICE_LABEL.get(c, c), {"type": "ruins_room", "c": c},
                                     KeyboardButtonColor.POSITIVE if i == 0 else KeyboardButtonColor.SECONDARY)
                                    for i, c in enumerate(options)]]
            rows += choice_rows
            exits = ruins_service.exits_now(run)
            arrow = [(texts.ARROWS[d], {"type": "ruins_step", "d": d}, KeyboardButtonColor.PRIMARY)
                     for d in ("left", "up", "down", "right") if d in exits]
            if choice_rows:
                rows.append(arrow)  # с выбором комнаты стрелки - одним рядом
            else:
                for line in (("up",), ("left", "right"), ("down",)):
                    row = [b for b in arrow if b[1]["d"] in line]
                    if row:
                        rows.append(row)
    if run.vote and cid != run.vote.get("target") and cid not in run.vote.get("yes", []) + run.vote.get("no", []):
        rows.append([(texts.BTN_VOTE_YES, {"type": "ruins_vote", "v": 1}, KeyboardButtonColor.NEGATIVE),
                     (texts.BTN_VOTE_NO, {"type": "ruins_vote", "v": 0}, KeyboardButtonColor.SECONDARY)])
    rows = [r for r in rows if r][:4]
    kb = Keyboard(one_time=False)
    for row in rows:
        for label, payload, color in row:
            kb.add(Text(label, payload=payload), color=color)
        kb.row()
    kb.add(Text(texts.BTN_BAG, payload={"type": "ruins_bag"}), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(texts.BTN_PARTY, payload={"type": "ruins_party"}), color=KeyboardButtonColor.SECONDARY)
    if len(rows) <= 3:
        _miniapp_link(kb)
    return kb.get_json()


def _miniapp_link(kb: Keyboard) -> None:
    """Мини-апп (еда едится оттуда) - своим рядом: VK пускает кнопку-ссылку
    только в ряд из двух кнопок, а с мешком и группой их было три - и VK
    отклонял каждое сообщение руин (2026-11-05, застряла Еста). Рядов всего
    не больше 5, поэтому при 4 рядах выбора ссылку не ставим."""
    from vkbottle import OpenLink

    from bot.keyboards.world import BTN_CHARACTER
    from config import get_settings

    url = get_settings().vk_miniapp_url
    if url:
        kb.row()
        kb.add(OpenLink(url, BTN_CHARACTER))


def keyboard_for(peer_id: int) -> str | None:
    """Синхронно клавиатуру не собрать (забег в базе) - для /клавиатура
    отвечает перехватчик сообщений."""
    return None


def _enter_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(texts.BTN_ENTER, payload={"type": "ruins_enter"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


# --- Клетка забоя -----------------------------------------------------------------


async def maybe_send_here_button(peer_id: int, character) -> None:
    """Предложение спуститься - отдельным сообщением под кнопкой забоя, раз
    на вход на клетку (как кнопка забоя)."""
    from bot import craft_button_state as cbs

    if (character.pos_x, character.pos_y) != rc.ENTRY_CELL or not ruins_service.open_for(peer_id):
        cbs.leave(peer_id, cbs.RUINS)
        return
    if is_inside(peer_id) or not cbs.should_send(peer_id, cbs.RUINS, *rc.ENTRY_CELL):
        return
    cbs.mark_sent(peer_id, cbs.RUINS, *rc.ENTRY_CELL)
    if character.level < rc.MIN_LEVEL:
        await _send(peer_id, texts.LOCKED_TEXT)
        return
    await _send(peer_id, texts.HERE_TEXT, keyboard=_enter_keyboard(), attachment=_pic("вход"))


async def _offer_again(peer_id: int) -> None:
    """После выхода или изгнания - кнопка спуска сразу, не дожидаясь, пока
    игрок уйдёт с клетки и вернётся."""
    from bot import craft_button_state as cbs

    cbs.mark_sent(peer_id, cbs.RUINS, *rc.ENTRY_CELL)
    await _send(peer_id, texts.AGAIN_TEXT, keyboard=_enter_keyboard())


_ENTRY_RE = re.compile(r"^\s*/(?:руины|ruins)\s*$", re.IGNORECASE)


@labeler.message(FuncRule(lambda m: bool(_ENTRY_RE.match(m.text or "")) and m.payload is None))
async def entry_command(message: Message) -> None:
    """«/руины»: на клетке забоя - кнопка спуска, внутри - вид комнаты."""
    if is_inside(message.peer_id):
        await _show_self(message)
        return
    if not ruins_service.open_for(message.from_id):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        cell, level = (character.pos_x, character.pos_y), character.level
        await db.commit()  # get_character пишет last_active_at
    if cell != rc.ENTRY_CELL:
        await message.answer(texts.NOT_HERE_TEXT)
    elif level < rc.MIN_LEVEL:
        await message.answer(texts.LOCKED_TEXT)
    else:
        await message.answer(texts.HERE_TEXT, keyboard=_enter_keyboard(), attachment=_pic("вход"))


# --- Вид комнаты ------------------------------------------------------------------


def _seen(run) -> dict[int, str]:
    rooms = rules.rooms_of(run.layout)
    out = {}
    for i in run.visited or []:
        kind = rooms.get(i)
        if kind is None:
            continue
        out[i] = kind if kind in (rules.BOSS, rules.START) or i not in (run.cleared or []) else "cleared"
    return out


def _view_text(run, cid: int, leader_name: str, head: str | None = None) -> str:
    lines = [head] if head else []
    lines.append(texts.floor_line(run.floor))
    kind = rules.room_kind(run.layout, run.pos)
    leader = run.leader_id == cid
    if run.offer:
        lines.append(texts.offer_text(run.offer.get("ids", []), leader, leader_name))
        return "\n".join(lines)
    if run.phase == ruins_service.CLEARED:
        # Зал хозяина: выбор, а ходить можно и дальше (2026-11-05).
        lines.append(texts.LEADER_CHOICE if leader else texts.WAIT_CHOICE)
    elif kind == rules.START:
        lines.append(texts.ROOM_TEXT[rules.START])
    elif ruins_service.room_open(run):
        if kind == rules.EVENT:
            lines.append(texts.EVENT_TEXT.get(rules.event_of(run.layout, run.pos) or "", "❓"))
        else:
            lines.append(texts.SPECIAL_TEXT.get(kind, ""))
        if kind == rules.WELL and not run.gifts:
            lines.append("Бросить в колодец нечего: даров у группы нет.")
        lines.append("Выбери действие кнопкой или иди дальше." if leader else f"Решает {leader_name}.")
    elif run.pos in (run.cleared or []):
        lines.append(texts.CLEARED_ROOM)
    if run.phase != ruins_service.CLEARED and ruins_service.boss_down(run):
        lines.append(texts.STAIRS_IN_BOSS_ROOM)
    lines.append(texts.exits_line(ruins_service.exits_now(run), _seen(run)))
    if run.pending:
        if leader:
            lines.append(texts.leader_wait_text(run.pending["dir"]))
        elif cid in run.pending.get("ok", []):
            lines.append("Ты готов идти. Ждём остальных.")
        else:
            lines.append(texts.pending_text(leader_name, run.pending["dir"]))
    elif not leader:
        lines.append(f"Ведёт {leader_name}.")
    return "\n".join(lines)


async def _broadcast_view(run_id: int, head: str | dict[int, str] | None = None,
                          photo: str | None = None) -> None:
    """Всем в забеге - где группа и что можно нажать. head - строка сверху
    (общая или своя каждому), photo - ключ картинки (ruins_config.PHOTOS)."""
    async with get_session_factory()() as db:
        run = await db.get(RuinRun, run_id)
        if run is None or run.status != ruins_service.ACTIVE:
            return
        await db.refresh(run)
        members = await ruins_service.members(db, run_id)
        peers = await _peers(db, [m.character_id for m in members])
        leader = await db.get(Character, run.leader_id)
        leader_name = leader.name if leader else "лидер"
    for cid, peer in peers.items():
        top = head.get(cid) if isinstance(head, dict) else head
        await _send(peer, _view_text(run, cid, leader_name, top), keyboard=_room_keyboard(run, cid),
                    attachment=_pic(photo))


# --- Вход -------------------------------------------------------------------------


@labeler.message(payload_contains={"type": "ruins_enter"})
@activity_action
async def enter(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if not ruins_service.open_for(message.from_id):
            return
        if (character.pos_x, character.pos_y) != rc.ENTRY_CELL:
            await message.answer("Вход в руины - в Подножном забое (-1; 0).")
            return
        group = await group_service.get_group_snapshot(db, character.id)
        if group is not None and group.leader_character_id != character.id:
            await message.answer("Повести группу в руины может только лидер.")
            return
        members = group.members if group is not None else [character]
        # Идут те, кто стоит у забоя (как у разломов): отставший не держит группу.
        going = [m for m in members if m.id == character.id
                 or ((m.pos_x, m.pos_y) == rc.ENTRY_CELL and m.travel_target_x is None)]
        left_behind = [m for m in members if m not in going]
        peers = await _peers(db, [c.id for c in going])
        for member in going:
            peer = peers.get(member.id)
            reason = await blocked_reason(db, member, peer) if peer is not None else "недоступен"
            if reason is None and peer is not None and is_inside(peer):
                reason = "уже в руинах"
            if reason is None and _busy_elsewhere(peer, member):
                reason = "занят"
            if reason:
                who = "Тебе" if member.id == character.id else member.name
                await message.answer(f"Спуск невозможен - {who}: {reason}")
                return
        try:
            run = await ruins_service.start(db, character, going, _rng)
        except ruins_service.RuinsError as exc:
            await db.rollback()
            await message.answer(str(exc))
            return
        await db.commit()
        run_id = run.id
        behind_peers = await _peers(db, [m.id for m in left_behind])
    for cid, peer in peers.items():
        _inside[peer] = run_id
        pvp_shield.drop(cid)
    for peer in behind_peers.values():
        await _send(peer, "Группа спустилась в руины без тебя: ты стоял не у забоя.")
    logger.info("Руины {}: спуск, {} человек", run_id, len(going))
    await _broadcast_view(run_id, texts.PROLOGUE, photo="пролог")


def _busy_elsewhere(peer_id: int | None, character) -> bool:
    from bot.handlers import raid_combat, rift, voyage

    if peer_id is None:
        return True
    return voyage.is_away(peer_id) or raid_combat.has_active_raid(character.id) or rift.is_waiting(peer_id)


# --- Перехват сообщений внутри ----------------------------------------------------


def _passes_through(message: Message) -> bool:
    if in_any_battle(message.peer_id):
        return True
    if is_info_command(message):
        return True
    payload = message.get_payload_json() or {}
    if isinstance(payload, dict) and str(payload.get("type", "")).startswith(("ruins_", "transfer_")):
        return True
    text = (message.text or "").strip().lower()
    return text.startswith(("/кик", "/kick", "/передать"))


INSIDE = FuncRule(lambda m: m.peer_id in _inside and not _passes_through(m))


async def _member_context(db, peer_id: int):
    """(забег под блокировкой, участник, персонаж) или None."""
    character = await onboarding_svc.get_character(db, peer_id)
    if character is None:
        return None
    member = await ruins_service.membership(db, character.id)
    if member is None:
        _inside.pop(peer_id, None)
        return None
    run = await ruins_service.lock(db, member.run_id)
    if run is None or run.status != ruins_service.ACTIVE:
        _inside.pop(peer_id, None)
        return None
    return run, member, character


async def _show_self(message: Message, head: str | None = None) -> None:
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        leader = await db.get(Character, run.leader_id)
        text = _view_text(run, character.id, leader.name if leader else "лидер", head)
        keyboard = _room_keyboard(run, character.id)
        await db.rollback()
    await message.answer(text, keyboard=keyboard)


@labeler.message(INSIDE)
async def while_inside(message: Message) -> None:
    await _show_self(message, texts.INSIDE_REMINDER)


# --- Ходьба -------------------------------------------------------------------------


@labeler.message(payload_contains={"type": "ruins_step"})
async def step(message: Message) -> None:
    direction = (message.get_payload_json() or {}).get("d")
    if direction not in rules.DIRS:
        return
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        party = len(await ruins_service.members(db, run.id))
        try:
            target = ruins_service.propose(run, character.id, direction, party)
        except ruins_service.RuinsError as exc:
            # Клавиатура - ДО отката: после него поля забега просрочены, и
            # чтение лезло в базу вне сессии (greenlet_spawn, 2026-11-05).
            keyboard = _room_keyboard(run, character.id)
            await db.rollback()
            await message.answer(str(exc), keyboard=keyboard)
            return
        await db.commit()
        run_id = run.id
    if party == 1:
        await _do_move(run_id, target)
    else:
        await _broadcast_view(run_id)


@labeler.message(payload_contains={"type": "ruins_go"})
async def go(message: Message) -> None:
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        if not run.pending:
            await db.rollback()
            await _show_self(message)
            return
        ruins_service.confirm(run, character.id)
        ids = [m.character_id for m in await ruins_service.members(db, run.id)]
        ready = ruins_service.all_confirmed(run, ids)
        target = run.pending["to"]
        await db.commit()
        run_id = run.id
    if ready:
        await _do_move(run_id, target)
    else:
        await _show_self(message)


async def _do_move(run_id: int, target: int, note: str | None = None) -> None:
    """Группа переходит в комнату target. С боем - бой сразу, с ловушкой -
    ловушка сразу."""
    trap_line = photo = None
    async with get_session_factory()() as db:
        run = await ruins_service.lock(db, run_id)
        if run is None or run.status != ruins_service.ACTIVE or run.phase not in (ruins_service.WALK,
                                                                                   ruins_service.CLEARED):
            return
        if run.pending and run.pending.get("to") != target:
            return
        kind = ruins_service.move(run, target)
        fight = run.phase == ruins_service.FIGHT
        if fight:
            await ruins_service.snapshot_hp(db, run)
        elif kind == rules.TRAP and target not in (run.cleared or []):
            dodged = await ruins_service.trap(db, run, _rng)
            names = {c: (await db.get(Character, c)).name for c in dodged}
            trap_line = texts.trap_text(dodged, names)
            photo = rc.ROOM_PHOTO_KEYS[rules.TRAP]
        else:
            photo = _room_photo(run)
        await db.commit()
    if fight:
        await _start_fight(run_id, note)
    else:
        head = "\n\n".join(x for x in (note, trap_line) if x) or None
        await _broadcast_view(run_id, head, photo)


async def _start_fight(run_id: int, note: str | None = None) -> None:
    from dataclasses import replace

    from bot.handlers import group_combat as group_combat_handlers
    from bot.handlers import raid_combat
    from game import ruins_gifts
    from game.combat.ruins import BossRoom, build_stage

    async with get_session_factory()() as db:
        run = await db.get(RuinRun, run_id)
        members = await ruins_service.members(db, run_id)
        characters = [c for c in [await db.get(Character, m.character_id) for m in members] if c is not None]
        inputs = await group_combat_handlers.build_member_inputs(db, characters)
        await db.commit()
        kind = ruins_service.fight_kind(run)
        hp = {m.character_id: (0 if m.dead else m.hp) for m in members}
        start = {m.character_id: ruins_service.battle_potions_start(run, m.consumables_used) for m in members}
        floor_used = {m.character_id: m.consumables_used for m in members}
        layout = dict(run.layout)
        gifts = list(run.gifts or [])
        extra = dict(run.extra or {})
    mods = ruins_gifts.mods(gifts)
    if mods:
        inputs = [replace(m, buff_modifiers={**m.buff_modifiers,
                                             **{k: m.buff_modifiers.get(k, 0.0) + v for k, v in mods.items()}})
                  for m in inputs]
    ctx = {"gifts": gifts, "kills": extra.get("kills", 0), "prayer_used": extra.get("prayer") or [],
           "start": start, "floor_used": floor_used}
    stage = build_stage(22_000_000, layout, kind, len(inputs), ctx, _rng)
    opening = (texts.boss_opening(stage.names) if isinstance(stage, BossRoom)
               else texts.opening_text(kind, layout, len(inputs)))
    if note:
        opening = f"{note}\n\n{opening}"
    try:
        await raid_combat.start_ruins_room(run_id, stage, inputs, hp, start, opening,
                                           attachment=_pic(_fight_photo(stage, kind, layout)))
    except Exception:
        logger.exception("Руины {}: бой не начался", run_id)
        async with get_session_factory()() as db:
            await ruins_service.recover(db)
            await db.commit()
        await _broadcast_view(run_id, texts.RESTART_TEXT)


# --- Итог боя комнаты ---------------------------------------------------------------


async def on_room_won(session_id: int, battle) -> None:
    from bot.handlers import raid_combat
    from game.combat.ruins import BossRoom

    stage = battle.ruin_stage
    combatants = raid_combat.release_ruins_battle(session_id)
    ctx = getattr(stage, "ctx", {}) or {}
    start, floor_used = ctx.get("start", {}), ctx.get("floor_used", {})
    hp, used, top = {}, {}, {}
    for cid in battle.participants:
        c = combatants.get(cid)
        if c is None:
            continue
        hp[cid] = c.current_hp if c.alive else 0
        top[cid] = c.max_hp
        spent = max(0, getattr(c, "consumables_used", 0) - start.get(cid, 0))
        used[cid] = floor_used.get(cid, 0) + spent
    reward = set(getattr(stage, "reward_ids", set()))
    kills = sum(1 for i in reward if combatants.get(i) is not None and not combatants[i].alive)
    bosses = len(stage.bosses) if isinstance(stage, BossRoom) else 0
    async with get_session_factory()() as db:
        run = await ruins_service.lock(db, battle.ruin_run_id)
        if run is None or run.status != ruins_service.ACTIVE:
            return
        found = await ruins_service.room_won(db, run, hp, used, _rng, kills=kills,
                                             prayer_used=list(getattr(stage, "prayer_used", []) or []),
                                             top_hp=top, bosses=bosses)
        boss = run.phase == ruins_service.CLEARED
        await db.commit()
        run_id = run.id
        floor = run.floor
    dailies = await _record_dailies(hp, top, floor)
    heads = {}
    for cid, got in found.items():
        lines = [texts.BOSS_DOWN] if boss else []
        line = texts.found_line(got)
        if line:
            lines.append(line)
        if got.get("chests"):
            lines.append(texts.chests_line(got["chests"]))
        heads[cid] = "\n".join(lines) or None
    await _broadcast_view(run_id, heads, "спуск" if boss else None)
    await _send_dailies(dailies)


async def _record_dailies(hp: dict[int, int], top: dict[int, int], floor: int) -> dict[int, object]:
    """Победа в комнате - выигранный бой для ежедневок, как групповой бой с
    мобами клетки (2026-11-06, репорт 323: «мобы своего уровня» не шли). Своя
    сессия - уже после коммита забега, блокировку забега не держим."""
    from game.combat.battle_report import BattleReport
    from services import daily_service

    out: dict[int, object] = {}
    try:
        async with get_session_factory()() as db:
            for cid, left in hp.items():
                if left <= 0:
                    continue
                character = await db.get(Character, cid)
                if character is None:
                    continue
                report = BattleReport(won=True, mob_level=rc.mob_level(floor), max_hp=top.get(cid, 0),
                                      hp_min_pct=1.0, only_skills=False, only_basic_attack=False)
                out[cid] = await daily_service.record_battle(db, character, report)
            await db.commit()
    except Exception:
        logger.exception("Руины: ежедневки после комнаты не записаны")
        return {}
    return out


async def _send_dailies(dailies: dict[int, object]) -> None:
    from bot import dailies_texts
    from bot.handlers import stats_window

    if not dailies:
        return
    async with get_session_factory()() as db:
        peers = await _peers(db, list(dailies))
    for cid, daily in dailies.items():
        peer = peers.get(cid)
        if peer is None:
            continue
        notice = dailies_texts.progress_notice(daily)
        if notice:
            await _send(peer, notice)
        for c in getattr(daily, "completed", []):
            await stats_window.notify_levelup(peer, c.levels_gained, c.new_level)


async def on_wipe(session_id: int, battle, text: str | None = None) -> None:
    from bot.handlers import raid_combat
    from bot.handlers import respawn as respawn_handlers
    from services import encounter_service

    raid_combat.release_ruins_battle(session_id)
    deaths = {}
    async with get_session_factory()() as db:
        run = await ruins_service.lock(db, battle.ruin_run_id)
        if run is None or run.status != ruins_service.ACTIVE:
            return
        ids = await ruins_service.wipe(db, run)
        for cid in ids:
            character = await db.get(Character, cid)
            if character is None:
                continue
            defeat = await encounter_service.resolve_defeat(db, character)
            deaths[cid] = (defeat, character.respawn_at)
        await db.commit()
        peers = await _peers(db, ids)
    body = f"{text}\n\n{texts.WIPE_TEXT}" if text else texts.WIPE_TEXT
    for cid, peer in peers.items():
        _inside.pop(peer, None)
        await _send(peer, body, attachment=_pic("гибель"))
        if cid in deaths:
            defeat, respawn_at = deaths[cid]
            await respawn_handlers.register_death(peer, respawn_at, defeat.xp_lost, defeat.relics_lost,
                                                  defeat.fish_lost)
    logger.info("Руины {}: группа погибла", battle.ruin_run_id)


# --- Особые комнаты и дары ----------------------------------------------------------


@labeler.message(payload_contains={"type": "ruins_room"})
async def room_choice(message: Message) -> None:
    choice = str((message.get_payload_json() or {}).get("c", ""))
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        try:
            result = await ruins_service.choose(db, run, character.id, choice, _rng)
        except ruins_service.RuinsError as exc:
            # Клавиатура - ДО отката: после него поля забега просрочены, и
            # чтение лезло в базу вне сессии (greenlet_spawn, 2026-11-05).
            keyboard = _room_keyboard(run, character.id)
            await db.rollback()
            await message.answer(str(exc), keyboard=keyboard)
            return
        if result["fight"]:
            await ruins_service.snapshot_hp(db, run)
        await db.commit()
        run_id = run.id
    lines = [texts.OUTCOME.get(k, "") for k in result["lines"] if texts.OUTCOME.get(k)]
    if result.get("curse"):
        lines.append(texts.curse_line(result["curse"]))
    head = "\n".join(lines) or None
    if result["fight"]:
        await _start_fight(run_id, head)
        return
    if result["loot"]:
        heads = {}
        for cid, drop in result["loot"].items():
            got = texts.trophies_line(drop) if drop else ""
            heads[cid] = "\n".join(x for x in (head, f"🎒 В мешок: {got}" if got else "") if x) or None
        await _broadcast_view(run_id, heads)
        return
    await _broadcast_view(run_id, head)


@labeler.message(payload_contains={"type": "ruins_gift"})
async def gift_pick(message: Message) -> None:
    gift_id = str((message.get_payload_json() or {}).get("g", ""))
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        if run.leader_id != character.id or not run.offer:
            await db.rollback()
            await _show_self(message)
            return
        try:
            ruins_service.take_gift(run, gift_id)
        except ruins_service.RuinsError as exc:
            await db.rollback()
            await message.answer(str(exc))
            return
        await db.commit()
        run_id = run.id
    await _broadcast_view(run_id, texts.gift_taken(gift_id, character.name))


async def _expire_offer(run_id: int) -> None:
    async with get_session_factory()() as db:
        run = await ruins_service.lock(db, run_id)
        if run is None or not ruins_service.offer_due(run):
            return
        gift_id = _rng.choice(run.offer["ids"])
        ruins_service.take_gift(run, gift_id)
        await db.commit()
    await _broadcast_view(run_id, texts.gift_taken(gift_id, None))


@labeler.message(payload_contains={"type": "ruins_act"})
async def boss_act(message: Message) -> None:
    """Особое действие в бою с боссом руин («Разгрести»): занимает ход."""
    from bot.battle_keyboard import answer_battle_gone
    from bot.handlers import raid_combat
    from game.combat.session import ActionType, DeclaredAction

    action_name = str((message.get_payload_json() or {}).get("a", ""))
    battle_id = raid_combat._peer_battle.get(message.peer_id)
    battle = raid_combat._battles.get(battle_id) if battle_id is not None else None
    if battle is None or not battle.is_ruins:
        await answer_battle_gone(message)
        return
    state = raid_combat._engine.sessions.get(battle_id)
    cid = raid_combat._character_id_for_peer(battle, message.peer_id)
    stage = battle.field_stage
    if state is None or cid is None or stage is None:
        return
    if cid in raid_combat._declared_this_tick.get(battle_id, set()):
        return
    note = stage.act(state, cid, action_name)
    if note is None:
        await message.answer("Сейчас никого не засыпало.")
        return
    await raid_combat._raid_action(
        message, DeclaredAction(type=ActionType.SKIP, payload={"note": note, action_name: True}),
    )


# --- После хозяина этажа --------------------------------------------------------------


@labeler.message(payload_contains={"type": "ruins_deeper"})
async def deeper(message: Message) -> None:
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        if run.leader_id != character.id or run.phase != ruins_service.CLEARED:
            head = texts.WAIT_CHOICE if run.phase == ruins_service.CLEARED else None
            await db.rollback()
            await _show_self(message, head)
            return
        await ruins_service.next_floor(db, run, _rng)
        await db.commit()
        run_id = run.id
    await _broadcast_view(run_id, f"⬇️ {character.name} ведёт группу ниже.")


@labeler.message(payload_contains={"type": "ruins_up"})
async def up(message: Message) -> None:
    from bot.handlers.raid_results import _send_location_summary

    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        if run.leader_id != character.id or run.phase != ruins_service.CLEARED:
            head = texts.WAIT_CHOICE if run.phase == ruins_service.CLEARED else None
            await db.rollback()
            await _show_self(message, head)
            return
        paid = await ruins_service.exit_run(db, run)
        await db.commit()
        peers = await _peers(db, list(paid))
        floor = run.floor
    for cid, peer in peers.items():
        _inside.pop(peer, None)
        pvp_shield.grant(cid, pvp_shield.RUINS, cell=rc.ENTRY_CELL)
        await _send(peer, f"{texts.EXIT_TEXT} Самый глубокий этаж: {floor}.\n{texts.exit_bag_line(paid[cid])}",
                    attachment=_pic("выход"))
        await _send_location_summary(cid, peer)
        await _offer_again(peer)
    logger.info("Руины {}: выход с этажа {}", run.id, floor)


# --- Мешок и группа -----------------------------------------------------------------


@labeler.message(payload_contains={"type": "ruins_bag"})
async def bag(message: Message) -> None:
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, member, character = ctx
        text = texts.bag_text(member.bag or {}, run.floor, member.consumables_used, ruins_service.floor_potions(run))
        gifts = texts.gifts_block(run.gifts or [])
        if gifts:
            text = f"{text}\n\n{gifts}"
        keyboard = _room_keyboard(run, character.id) if run.phase != ruins_service.FIGHT else None
        await db.rollback()
    await message.answer(text, keyboard=keyboard)


@labeler.message(payload_contains={"type": "ruins_party"})
async def party(message: Message) -> None:
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        rows = []
        for m in await ruins_service.members(db, run.id):
            c = await db.get(Character, m.character_id)
            if c is None:
                continue
            _, max_hp = await ruins_service.world_hp(db, c)
            rows.append((c.name, m.hp, max_hp, m.dead, m.character_id == run.leader_id))
        keyboard = _room_keyboard(run, character.id) if run.phase != ruins_service.FIGHT else None
        await db.rollback()
    await message.answer(texts.party_text(rows), keyboard=keyboard)


# --- /кик -----------------------------------------------------------------------------

_KICK_RE = re.compile(r"^\s*/(?:кик|kick)\s+(.+?)\s*$", re.IGNORECASE)


@labeler.message(FuncRule(lambda m: bool(_KICK_RE.match(m.text or "")) and m.payload is None))
async def kick_command(message: Message) -> None:
    from datetime import datetime, timedelta, timezone

    nick = _KICK_RE.match(message.text or "").group(1).strip().lower()
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            await message.answer(texts.KICK_ONLY_INSIDE)
            return
        run, _member, character = ctx
        members = await ruins_service.members(db, run.id)
        chars = {m.character_id: await db.get(Character, m.character_id) for m in members}
        target = next((c for c in chars.values() if c is not None and c.name.lower() == nick), None)
        problem = None
        if len(members) < 2:
            problem = texts.KICK_SOLO
        elif target is None or target.id == character.id:
            problem = texts.KICK_ONLY_INSIDE
        elif run.phase == ruins_service.FIGHT:
            problem = texts.KICK_NOT_IN_FIGHT
        elif run.vote:
            problem = texts.KICK_BUSY
        if problem:
            await db.rollback()
            await message.answer(problem)
            return
        until = datetime.now(timezone.utc) + timedelta(seconds=rc.KICK_VOTE_SECONDS)
        run.vote = {"target": target.id, "until": until.isoformat(), "yes": [character.id], "no": [],
                    "starter": character.name}
        ruins_service.touch(run)
        done = _vote_decided(run, len(members))
        await db.commit()
        run_id = run.id
    if done:
        await _finish_vote(run_id)
    else:
        await _broadcast_view(run_id, texts.vote_text(character.name, target.name))


def _vote_decided(run, party: int) -> bool:
    """Большинство остальных (без изгоняемого) - за, или голосовать больше некому."""
    vote = run.vote or {}
    voters = party - 1
    yes, no = len(vote.get("yes", [])), len(vote.get("no", []))
    return yes * 2 > voters or no * 2 >= voters or yes + no >= voters


@labeler.message(payload_contains={"type": "ruins_vote"})
async def vote(message: Message) -> None:
    value = (message.get_payload_json() or {}).get("v")
    async with get_session_factory()() as db:
        ctx = await _member_context(db, message.peer_id)
        if ctx is None:
            return
        run, _member, character = ctx
        if not run.vote or character.id == run.vote.get("target"):
            await db.rollback()
            await _show_self(message)
            return
        yes = [c for c in run.vote.get("yes", []) if c != character.id]
        no = [c for c in run.vote.get("no", []) if c != character.id]
        (yes if value else no).append(character.id)
        run.vote = {**run.vote, "yes": yes, "no": no}
        done = _vote_decided(run, len(await ruins_service.members(db, run.id)))
        await db.commit()
        run_id = run.id
    if done:
        await _finish_vote(run_id)
    else:
        await _show_self(message, "Голос учтён.")


async def _finish_vote(run_id: int) -> None:
    from bot.handlers.raid_results import _send_location_summary

    async with get_session_factory()() as db:
        run = await ruins_service.lock(db, run_id)
        if run is None or not run.vote:
            return
        party = len(await ruins_service.members(db, run_id))
        vote = run.vote
        run.vote = None
        target = await db.get(Character, vote["target"])
        passed = len(vote.get("yes", [])) * 2 > party - 1
        old_leader = run.leader_id
        if passed and target is not None:
            await ruins_service.kick(db, run, target.id)
        await db.commit()
        new_leader = await db.get(Character, run.leader_id) if run.leader_id != old_leader else None
        target_peer = await onboarding_svc.vk_id_for_character(db, target.id) if target else None
        target_name = target.name if target else "?"
        target_id = target.id if target else None
    if not passed:
        await _broadcast_view(run_id, texts.KICK_FAILED.format(name=target_name))
        return
    if target_peer is not None:
        _inside.pop(target_peer, None)
        await _send(target_peer, texts.KICKED_TEXT)
        await _send_location_summary(target_id, target_peer)
        await _offer_again(target_peer)
    head = texts.kicked_others(target_name)
    if new_leader is not None:
        head += "\n" + texts.new_leader(new_leader.name)
    await _broadcast_view(run_id, head)


# --- Фон: шаги без подтверждения, голосования, брошенные забеги ----------------------


async def tick_job() -> None:
    if _bot_api is None:
        return
    try:
        async with get_session_factory()() as db:
            runs = await ruins_service.active_runs(db)
            due_moves = [(r.id, r.pending["to"]) for r in runs if ruins_service.pending_due(r)]
            due_votes = [r.id for r in runs if r.vote and _vote_due(r.vote)]
            due_offers = [r.id for r in runs if ruins_service.offer_due(r)]
        for run_id in due_offers:
            await _expire_offer(run_id)
        for run_id, target in due_moves:
            await _do_move(run_id, target, texts.MOVE_TIMEOUT_NOTE)
        for run_id in due_votes:
            await _finish_vote(run_id)
        async with get_session_factory()() as db:
            gone = await ruins_service.abandon_due(db)
            await db.commit()
            for _run_id, ids in gone:
                for cid, peer in (await _peers(db, ids)).items():
                    _inside.pop(peer, None)
                    await _send(peer, texts.ABANDON_TEXT)
    except Exception:
        logger.exception("Руины: тик не прошёл")


def _vote_due(vote: dict) -> bool:
    from datetime import datetime, timezone

    return datetime.fromisoformat(vote["until"]) <= datetime.now(timezone.utc)


async def recover_on_start() -> None:
    """При старте бота: кто внутри - снова в памяти; бой, оборванный
    перезапуском, отыгрывается заново из комнаты, откуда шли."""
    async with get_session_factory()() as db:
        fighting = {r.id for r in await ruins_service.active_runs(db) if r.phase == ruins_service.FIGHT}
        runs = await ruins_service.recover(db)
        await db.commit()
        for run in runs:
            ids = [m.character_id for m in await ruins_service.members(db, run.id)]
            for peer in (await _peers(db, ids)).values():
                _inside[peer] = run.id
    for run_id in fighting:
        await _broadcast_view(run_id, texts.RESTART_TEXT)
