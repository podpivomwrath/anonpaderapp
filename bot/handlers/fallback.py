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
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»


#: Ответ на нажатие/текст, который никто не понял.
STALE_TEXT = "Эта кнопка устарела - кнопки обновлены."


@labeler.message()
async def fallback(message: Message) -> None:
    from datetime import datetime, timezone

    from bot.handlers import world as world_handlers

    async with get_session_factory()() as db:
        character = await get_character(db, message.from_id)
        if character is None:
            await handle_start(message)
            return
        # Только личный диалог: в беседе (peer_id беседы != from_id) бот
        # ответил бы на каждую реплику игроков.
        if character.creation_state is not None or message.peer_id != message.from_id:
            return
        # Набранный текст, который никто не понял, - молчим (2026-10-21,
        # владелец). «Кнопки обновлены» - только на нажатие кнопки.
        if message.payload is None:
            return
        # Нажатие, которое никто не обработал, - почти всегда кнопка из
        # старой клавиатуры (после рестарта, после смены экрана). Раньше бот
        # молчал, и игрок жал её снова и снова (2026-10-13). Теперь - свежая
        # клавиатура под текущее состояние.
        keyboard = await world_handlers._current_keyboard(
            db, character, message.peer_id, datetime.now(timezone.utc),
        )
    await message.answer(STALE_TEXT, keyboard=keyboard)
