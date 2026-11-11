"""Кнопка «📢 Показать союзникам» в групповом бою (bot/battle_signals.py)."""

from vkbottle.bot import BotLabeler, Message

from bot import battle_signals

labeler = BotLabeler()
labeler.vbml_ignore_case = True


@labeler.message(payload_contains={"type": battle_signals.PAYLOAD_TYPE})
async def show_to_allies(message: Message) -> None:
    text, keyboard = await battle_signals.send(message.ctx_api, message.peer_id)
    if keyboard is None:
        await message.answer(text)
    else:
        await message.answer(text, keyboard=keyboard)
