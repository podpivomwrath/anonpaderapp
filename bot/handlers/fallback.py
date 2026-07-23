"""Отлов сообщений, не подошедших ни одному хендлеру.

Если у игрока нет персонажа (например, после дев-вайпа) — начинаем
онбординг заново, как требует дизайн: "при следующем сообщении
автоматически попадает на онбординг". ДОЛЖЕН быть загружен ПОСЛЕДНИМ
в LABELERS — иначе перехватит всё раньше специфичных хендлеров.
"""

from vkbottle.bot import BotLabeler, Message

from bot.handlers.onboarding import handle_start
from services.db import get_session_factory
from services.onboarding_service import get_character

labeler = BotLabeler()


@labeler.message()
async def fallback(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await get_character(db, message.from_id)
    if character is None:
        await handle_start(message)
