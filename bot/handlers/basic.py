"""Базовые команды. /start живёт в onboarding.py (FSM создания персонажа)."""

from vkbottle import Keyboard
from vkbottle.bot import BotLabeler, Message

from bot.battle_keyboard import active_battle_keyboard
from bot.keyboards.world import add_miniapp_button
from services.db import get_session_factory
from services.user_service import get_profile_text

labeler = BotLabeler()


@labeler.message(text=["/profile", "profile", "профиль", "Профиль"])
async def handle_profile(message: Message) -> None:
    async with get_session_factory()() as session:
        text = await get_profile_text(session, vk_id=message.from_id)

    if text is None:
        await message.answer(
            "Персонаж не найден или создание не завершено. Напиши /start."
        )
        return

    # Патч 30, баг 2: справочная команда не должна стирать боевую клавиатуру,
    # если игрок сейчас в PvE/PvP-бою.
    battle_kb = active_battle_keyboard(message.peer_id)
    if battle_kb is not None:
        await message.answer(text, keyboard=battle_kb)
        return

    # Клавиатуру шлём только если мини-апп настроен — иначе пустая
    # клавиатура затёрла бы уже показанные игроку кнопки города/мира.
    kb = Keyboard(one_time=False, inline=True)
    add_miniapp_button(kb)
    keyboard = kb.get_json() if kb.buttons and kb.buttons[0] else None
    await message.answer(text, keyboard=keyboard)
