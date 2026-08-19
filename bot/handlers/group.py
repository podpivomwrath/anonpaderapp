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

from vkbottle.bot import BotLabeler, Message

from bot.keyboards.group import group_invite_keyboard, leave_confirm_keyboard
from bot import group_texts
from services import group_service as gs
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

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
        try:
            result = await gs.leave_group(db, character.id)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
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
    if result.dissolved:
        return
    for vk_id in remaining_peer_ids:
        text = f"👥 {left_name} покинул группу."
        if new_leader_name is not None:
            text += f" Новый лидер: 👑 {new_leader_name}."
        try:
            await _bot_api.messages.send(peer_id=vk_id, message=text, random_id=0)
        except Exception:
            pass


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
        try:
            result = await gs.kick_member(db, leader, target.id)
        except gs.GroupError as exc:
            await message.answer(str(exc))
            return
        await db.commit()
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
