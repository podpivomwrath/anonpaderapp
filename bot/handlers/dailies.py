"""Ежедневные задания в чате (патч 23): команда /ежедневки (и /daily),
кнопка [📜 Задания] в городе — то же самое. Мини-апп (вкладка «Задания») —
основной интерфейс, это дублирующий доступ из чата (см. патч, п.7).
"""

from vkbottle.bot import BotLabeler, Message

from bot import info_reply
from bot import dailies_texts
from bot.dispatch_rules import is_info_command
from bot.keyboards.world import BTN_DAILIES
from services import daily_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»


@labeler.message(text=[BTN_DAILIES, "/ежедневки", "/daily"])
async def show_dailies(message: Message) -> None:
    from datetime import datetime, timezone

    from bot.handlers import world as world_handlers  # избегаем цикла импортов

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        overview = await daily_service.get_dailies_overview(db, character)
        # Клавиатура текущего состояния (бой, город, поле): без неё ответ на
        # /daily оставлял игрока без кнопок (2026-10-14).
        # Набранная /daily - справка: клавиатуру не трогает (2026-10-16), в бою - боевая.
        if is_info_command(message):
            keyboard = None  # ниже, вне сессии: bot/info_reply.py
        else:
            keyboard = await world_handlers._current_keyboard(
                db, character, message.peer_id, datetime.now(timezone.utc),
            )
    if is_info_command(message):
        keyboard = await info_reply.keyboard_for(message.peer_id, message.from_id)
    await message.answer(dailies_texts.dailies_overview_text(overview), keyboard=keyboard)
