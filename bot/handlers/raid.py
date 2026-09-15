"""Рейд-лобби (патч 53): кнопка «Прикоснуться» на клетке Монолита (0;0),
экран выбора рейда, сбор группы, старт боя. Сам бой — bot/handlers/
raid_combat.py (этот модуль его не знает, только запускает)."""

import random

from vkbottle.bot import BotLabeler, Message

from bot import raid_texts as rt
from bot.handlers import group_combat as group_combat_handlers
from bot.handlers import raid_combat as raid_combat_handlers
from bot.keyboards import raid as kb
from bot.keyboards.world import movement_keyboard
from game.economy import raid_config as rc
from game.world import grid
from services import group_service, mount_service
from services import onboarding_service as onboarding_svc
from services import raid_service as rs
from services import screen_service
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_rng = random.Random()

# Патч 53: регистрирует новый вложенный экран в общей таблице патча 37 —
# [← Назад] с него ведёт на корень (город/карта), как и у большинства
# вложенных экранов вне города.
screen_service.PARENT["raid_list"] = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def _peer_ids_for(db, character_ids: list[int]) -> dict[int, int]:
    result = {}
    for cid in character_ids:
        peer_id = await onboarding_svc.vk_id_for_character(db, cid)
        if peer_id is not None:
            result[cid] = peer_id
    return result


@labeler.message(payload_contains={"type": "raid_touch"})
async def touch_monolith(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.chebyshev_distance(character.pos_x, character.pos_y) != 0:
            return  # устаревшая кнопка — уже не на (0;0)
        await screen_service.set_screen(db, character, "raid_list")
        await db.commit()
    await message.answer(rt.RAID_LIST_TEXT, keyboard=kb.raid_list_keyboard())


async def _back_to_movement(message: Message, text: str) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        await screen_service.set_screen(db, character, None)
        await db.commit()
        has_mount = await mount_service.has_any_mount(db, character.id)
    await message.answer(
        text, keyboard=movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
    )


@labeler.message(text=[rt.BTN_RAID_BACK])
async def raid_list_back_button(message: Message) -> None:
    await _back_to_movement(message, "Ты отступаешь от Монолита.")


@labeler.message(payload_contains={"type": "raid_list_back"})
async def raid_list_back_payload(message: Message) -> None:
    await _back_to_movement(message, "Ты отступаешь от Монолита.")


@labeler.message(payload_contains={"type": "raid_pick"})
async def pick_raid(message: Message) -> None:
    payload = message.get_payload_json() or {}
    raid_id = payload.get("raid")
    if raid_id != rc.RAID_PUPPET_THEATRE_ID:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.chebyshev_distance(character.pos_x, character.pos_y) != 0:
            await message.answer("Ты уже не у Монолита.")
            return
        if raid_combat_handlers.has_active_raid(character.id):
            await message.answer("Ты уже в рейде.")
            return
        group_snapshot = await group_service.get_group_snapshot(db, character.id)
        group_id = group_snapshot.id if group_snapshot is not None else None
        try:
            snapshot = await rs.touch_monolith(db, character, raid_id, group_id)
        except rs.RaidError as exc:
            await db.commit()
            await message.answer(str(exc))
            return

        is_leader_first = len(snapshot.members) == 1
        ready = rs.is_ready_to_start(snapshot)
        leader_name = character.name
        notify_peer_ids = []
        if group_id is not None and is_leader_first and group_snapshot is not None:
            notify_peer_ids = list(
                (await _peer_ids_for(db, [m.id for m in group_snapshot.members if m.id != character.id])).values()
            )
        await db.commit()

    for peer_id in notify_peer_ids:
        try:
            await _bot_api.messages.send(peer_id=peer_id, message=rt.group_touch_notice(leader_name), random_id=0)
        except Exception:
            pass

    ready_count = sum(1 for _, r in snapshot.members if r)
    await message.answer(rt.lobby_status_line(ready_count, snapshot.denominator), keyboard=kb.raid_lobby_keyboard())

    if ready:
        await _start_raid_from_lobby(snapshot.id)


@labeler.message(payload_contains={"type": "raid_cancel_ready"})
async def cancel_ready(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        snapshot = await rs.cancel_readiness(db, character.id)
        await db.commit()
        if snapshot is None:
            has_mount = await mount_service.has_any_mount(db, character.id)
    if snapshot is None:
        await message.answer(
            "Готовность снята.",
            keyboard=movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
        )
        return
    ready_count = sum(1 for _, r in snapshot.members if r)
    await message.answer(rt.lobby_status_line(ready_count, snapshot.denominator), keyboard=kb.raid_lobby_keyboard())


async def _start_raid_from_lobby(lobby_id: int) -> None:
    async with get_session_factory()() as db:
        snapshot = await rs.get_snapshot(db, lobby_id)
        if snapshot is None or not rs.is_ready_to_start(snapshot):
            return
        leader = next((c for c, _ in snapshot.members if c.id == snapshot.leader_character_id), None)
        if leader is None:
            return
        ok = await rs.consume_key_and_start(db, leader)
        if not ok:
            await rs.dissolve_lobby(db, lobby_id)
            peer_ids = await _peer_ids_for(db, [c.id for c, _ in snapshot.members])
            leader_id = leader.id
            await db.commit()
            await db.close()
            for cid, peer_id in peer_ids.items():
                text = rt.NO_KEY_TEXT if cid == leader_id else "Рейд не начался — у лидера не нашлось Ключа Монолита."
                try:
                    await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0)
                except Exception:
                    pass
            return

        await rs.start_lobby(db, lobby_id)
        member_inputs = await group_combat_handlers.build_member_inputs(db, [c for c, _ in snapshot.members])
        group_id = snapshot.group_id
        await rs.dissolve_lobby(db, lobby_id)
        await db.commit()
        await db.close()

    await raid_combat_handlers.start_raid(group_id, member_inputs, _rng)
