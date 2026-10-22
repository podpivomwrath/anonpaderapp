"""Кнопка «📜 Сводка» / «📜 Скрыть» короткого боевого лога (bot/short_log.py)."""

from vkbottle.bot import BotLabeler, Message

from bot import short_log

labeler = BotLabeler()
labeler.vbml_ignore_case = True


@labeler.message(payload_contains={"type": short_log.PAYLOAD_TYPE})
async def toggle_log(message: Message) -> None:
    if not await short_log.toggle(message.ctx_api, message.peer_id):
        await message.answer(short_log.NOTHING_TEXT)
