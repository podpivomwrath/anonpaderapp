"""Кнопки короткого боевого лога (bot/short_log.py): «📜 Сводка» / «📜 Скрыть»
в нижней клавиатуре - для текущего хода, «📜 Подробнее» / «📜 Свернуть» под
прошлыми логами боя - callback, нажатие ничего не пишет в чат."""

import json

from loguru import logger
from vkbottle import GroupEventType, GroupTypes
from vkbottle.bot import BotLabeler, Message

from bot import short_log
from bot.battle_keyboard import in_any_battle

labeler = BotLabeler()
labeler.vbml_ignore_case = True


@labeler.message(payload_contains={"type": short_log.PAYLOAD_TYPE})
async def toggle_log(message: Message) -> None:
    if not await short_log.toggle(message.ctx_api, message.peer_id):
        await message.answer(short_log.NOTHING_TEXT)


@labeler.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def toggle_log_inline(event: GroupTypes.MessageEvent) -> None:
    obj = event.object
    payload = obj.payload if isinstance(obj.payload, dict) else {}
    if payload.get("type") != short_log.CALLBACK_TYPE or not isinstance(payload.get("m"), int):
        return
    note = await short_log.toggle_inline(event.ctx_api, obj.peer_id, payload["m"], in_any_battle(obj.peer_id))
    # Ответ на нажатие обязателен, иначе у игрока крутится кнопка.
    try:
        await event.ctx_api.messages.send_message_event_answer(
            event_id=obj.event_id, user_id=obj.user_id, peer_id=obj.peer_id,
            event_data=json.dumps({"type": "show_snackbar", "text": note}, ensure_ascii=False) if note else None,
        )
    except Exception:  # noqa: BLE001 - лог уже поправлен, подсказка - мелочь
        logger.warning("Короткий лог: ответ на кнопку не дошёл {}", obj.peer_id)
