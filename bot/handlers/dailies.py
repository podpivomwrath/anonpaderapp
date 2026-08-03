"""Ежедневные задания в чате (патч 23): команда /ежедневки (и /daily),
кнопка [📜 Задания] в городе — то же самое. Мини-апп (вкладка «Задания») —
основной интерфейс, это дублирующий доступ из чата (см. патч, п.7).
"""

from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts
from bot.keyboards.world import BTN_DAILIES
from services import daily_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()


@labeler.message(text=[BTN_DAILIES, "/ежедневки", "/daily"])
async def show_dailies(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        overview = await daily_service.get_dailies_overview(db, character)
    await message.answer(dailies_texts.dailies_overview_text(overview))
