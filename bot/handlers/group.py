"""Группы (патч 51, ч.2): приглашение (командой или пересылкой сообщения с
подписью «пригласить»), принятие/отклонение прямо в приглашении, выход с
подтверждением, исключение лидером.

Действие подчиняется общей цепочке приоритета разбора ввода (правило патчей
40/42, см. bot/dispatch_rules.py): текстовые команды здесь конкретные
(требуют точный текст "пригласить"/"/выйти" или префикс "пригласить <ник>"),
поэтому не пересекаются со свободным вводом координат/никнейма — но регистр
модуля в LABELERS всё равно СТРОГО ДО promo_labeler (bot/handlers/promo.py):
одиночное слово "пригласить" технически проходит под тот же regex, что и
код промо, и без явного порядка функция приглашения могла бы быть перехвачена
угадавшим совпадение промокодом."""

import asyncio

from vkbottle.bot import BotLabeler, Message

from bot.keyboards.group import group_invite_keyboard, leave_confirm_keyboard
from bot import group_texts
from game.world import grid
from services import group_explore_service
from services import group_service as gs
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

_bot_api = None

USAGE_TEXT = (
    "Чтобы пригласить в группу: напиши «пригласить Никнейм» или перешли "
    "сообщение игрока боту с подписью «пригласить»."
)
NOT_FOUND_TEXT = "Игрок с таким ником не найден."


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def _send_invite(message: Message, nickname: str) -> None:
    async with get_session_factory()() as db:
        inviter = await onboarding_svc.get_character(db, message.from_id)
        if inviter is None or inviter.creation_state is not None:
            return
        target = await gs.find_character_by_name(db, nickname)
        if target is None or target.creation_state is not None:
            await message.answer(NOT_FOUND_TEXT)
            return
        try:
            invite = await gs.send_invite(db, inviter, target)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
        target_peer_id = await onboarding_svc.vk_id_for_character(db, target.id)
        inviter_name = inviter.name

    await message.answer(f"👥 Приглашение отправлено игроку {target.name}. У него есть 1 минута на ответ.")
    if target_peer_id is not None:
        await _bot_api.messages.send(
            peer_id=target_peer_id,
            message=f"👥 {inviter_name} приглашает тебя в группу.",
            random_id=0,
            keyboard=group_invite_keyboard(invite.id),
        )


@labeler.message(text=["пригласить <name>", "/invite <name>"])
async def invite_by_name(message: Message, name: str) -> None:
    await _send_invite(message, name)


@labeler.message(text=["пригласить"])
async def invite_by_forward(message: Message) -> None:
    """Пересылка сообщения игрока боту с подписью «пригласить» — id
    отправителя берётся из fwd_messages/reply_message (vkbottle Message)."""
    from_vk_id = None
    if message.reply_message is not None:
        from_vk_id = message.reply_message.from_id
    elif message.fwd_messages:
        from_vk_id = message.fwd_messages[0].from_id
    if from_vk_id is None:
        await message.answer(USAGE_TEXT)
        return

    async with get_session_factory()() as db:
        inviter = await onboarding_svc.get_character(db, message.from_id)
        if inviter is None or inviter.creation_state is not None:
            return
        target = await onboarding_svc.get_character(db, from_vk_id)
        if target is None or target.creation_state is not None:
            await message.answer(NOT_FOUND_TEXT)
            return
        try:
            invite = await gs.send_invite(db, inviter, target)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
        inviter_name = inviter.name
        target_name = target.name

    await message.answer(f"👥 Приглашение отправлено игроку {target_name}. У него есть 1 минута на ответ.")
    await _bot_api.messages.send(
        peer_id=from_vk_id,
        message=f"👥 {inviter_name} приглашает тебя в группу.",
        random_id=0,
        keyboard=group_invite_keyboard(invite.id),
    )


@labeler.message(payload_contains={"type": "group_invite_accept"})
async def invite_accept(message: Message) -> None:
    payload = message.get_payload_json() or {}
    invite_id = payload.get("invite_id")
    if not isinstance(invite_id, int):
        return
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            result = await gs.accept_invite(db, invite_id, character.id)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
        group_block = await group_texts.group_summary_block(db, character.id)
        leader = next(m for m in result.group.members if m.id == result.group.leader_character_id)
        leader_peer_id = await onboarding_svc.vk_id_for_character(db, leader.id)
        joined_name = character.name

    await message.answer(f"👥 Ты вступил в группу.\n\n{group_block}")
    if leader_peer_id is not None and leader_peer_id != peer_id:
        await _bot_api.messages.send(
            peer_id=leader_peer_id,
            message=f"👥 {joined_name} вступил в группу.\n\n{group_block}",
            random_id=0,
        )


@labeler.message(payload_contains={"type": "group_invite_decline"})
async def invite_decline(message: Message) -> None:
    payload = message.get_payload_json() or {}
    invite_id = payload.get("invite_id")
    if not isinstance(invite_id, int):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            await gs.decline_invite(db, invite_id, character.id)
        except gs.GroupError:
            return
        await db.commit()

    await message.answer("Приглашение отклонено.")


@labeler.message(text=["/выйти", "/leave"])
async def leave_prompt(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await gs.get_membership(db, character.id) is None:
            await message.answer("Ты не в группе.")
            return
    await message.answer("Точно выйти из группы?", keyboard=leave_confirm_keyboard())


@labeler.message(payload_contains={"type": "group_leave_confirm"})
async def leave_confirm(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        membership = await gs.get_membership(db, character.id)
        try:
            result = await gs.leave_group(db, character.id)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
        hint_peers = await _drop_from_explore_queue(db, membership, character.id, result.dissolved)
        remaining_peer_ids = []
        for cid in result.remaining_member_character_ids:
            vk_id = await onboarding_svc.vk_id_for_character(db, cid)
            if vk_id is not None:
                remaining_peer_ids.append(vk_id)
        left_name = character.name
        new_leader_name = None
        if result.new_leader_character_id is not None:
            from models import Character

            new_leader = await db.get(Character, result.new_leader_character_id)
            new_leader_name = new_leader.name if new_leader is not None else None

    await message.answer("Ты вышел из группы.")
    for vk_id in remaining_peer_ids:
        if result.dissolved:
            # Группа распадается, когда остаётся один. Сказать об этом надо:
            # иначе последний участник видит «группа» на экране и не понимает,
            # почему она больше ничего не умеет.
            text = f"👥 {left_name} покинул группу. Группа распалась - ты остался один."
        else:
            text = f"👥 {left_name} покинул группу."
            if new_leader_name is not None:
                text += f" Новый лидер: 👑 {new_leader_name}."
        try:
            await _bot_api.messages.send(peer_id=vk_id, message=text, random_id=0)
        except Exception:
            pass
    from bot.handlers import world as world_handlers

    await world_handlers.send_ready_hint(hint_peers)


async def _drop_from_explore_queue(db, membership, character_id: int, dissolved: bool) -> list[int]:
    """Ушедший из группы выпадает из очереди группового исследования - иначе
    остальные ждут его вечно. Распалась - очереди больше нет. Возвращает, кому
    сказать «нажми ещё раз» (очередь собралась без него)."""
    if membership is None:
        return []
    if dissolved:
        group_explore_service.clear(membership.group_id)
        return []
    from bot.handlers import world as world_handlers

    ready = group_explore_service.cancel(membership.group_id, character_id)
    return await world_handlers.ready_hint_peers(db, ready)


@labeler.message(payload_contains={"type": "group_leave_cancel"})
async def leave_cancel(message: Message) -> None:
    await message.answer("Отменено.")


@labeler.message(text=["/выгнать <name>", "/kick <name>"])
async def kick_by_name(message: Message, name: str) -> None:
    async with get_session_factory()() as db:
        leader = await onboarding_svc.get_character(db, message.from_id)
        if leader is None or leader.creation_state is not None:
            return
        target = await gs.find_character_by_name(db, name)
        if target is None:
            await message.answer(NOT_FOUND_TEXT)
            return
        membership = await gs.get_membership(db, target.id)
        try:
            kicked = await gs.kick_member(db, leader, target.id)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
        hint_peers = await _drop_from_explore_queue(
            db, membership, target.id, kicked.dissolved,
        )
        target_peer_id = await onboarding_svc.vk_id_for_character(db, target.id)
        target_name = target.name

    await message.answer(f"👥 {target_name} исключён из группы.")
    if target_peer_id is not None:
        try:
            await _bot_api.messages.send(
                peer_id=target_peer_id, message="👥 Тебя исключили из группы.", random_id=0,
            )
        except Exception:
            pass
    from bot.handlers import world as world_handlers

    await world_handlers.send_ready_hint(hint_peers)


# --- Вести группе (2026-10-12) ---------------------------------------------------


async def _member_peers(db, members) -> list[int]:
    peers = []
    for member in members:
        vk_id = await onboarding_svc.vk_id_for_character(db, member.id)
        if vk_id is not None:
            peers.append(vk_id)
    return peers


def _send_later(peers: list[int], text: str) -> None:
    """Вести не держат сессию и вызывающего: отправка - отдельной задачей."""
    if not peers or _bot_api is None:
        return

    async def run() -> None:
        for peer in peers:
            try:
                await _bot_api.messages.send(peer_id=peer, message=text, random_id=0)
            except Exception:
                pass

    asyncio.get_running_loop().create_task(run())


async def notify_arrival(db, character) -> None:
    """Участник группы пришёл на клетку, где стоят другие из его группы, - они
    узнают. В городе молчим: там стоит полгруппы сразу, и каждый вход на
    площадь был бы вестью."""
    if grid.city_region_at(character.pos_x, character.pos_y) is not None:
        return
    snapshot = await gs.get_group_snapshot(db, character.id)
    if snapshot is None:
        return
    from services import mount_service

    here = []
    for m in snapshot.members:
        if m.id == character.id or (m.pos_x, m.pos_y) != (character.pos_x, character.pos_y):
            continue
        # Кто сам едет верхом, лишь проезжает эту клетку - ему весть ни к чему.
        travel = await mount_service.active_travel(db, m.id)
        if travel is not None and travel.status == "traveling":
            continue
        here.append(m)
    peers = await _member_peers(db, here)
    _send_later(peers, f"👥 {character.name} теперь на твоей клетке ({character.pos_x}; {character.pos_y}).")


async def notify_attacked(db, victim, attacker) -> None:
    """На участника группы напал игрок - узнаёт вся группа, где бы ни была."""
    snapshot = await gs.get_group_snapshot(db, victim.id)
    if snapshot is None:
        return
    others = [m for m in snapshot.members if m.id not in (victim.id, attacker.id)]
    peers = await _member_peers(db, others)
    _send_later(
        peers,
        f"⚔️ На {victim.name} из твоей группы напал {attacker.name} - клетка ({victim.pos_x}; {victim.pos_y}).",
    )
