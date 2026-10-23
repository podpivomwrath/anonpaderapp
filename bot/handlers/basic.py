"""Базовые команды. /start живёт в onboarding.py (FSM создания персонажа)."""

from vkbottle import Keyboard
from vkbottle.bot import BotLabeler, Message

from bot import info_reply
from bot.keyboards.world import add_miniapp_button
from services.db import get_session_factory
from services.user_service import get_profile_text

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»


#: Все команды бота (2026-10-21). Новая команда - строка сюда, иначе
#: tests/test_help_command.py напомнит.
HELP_TEXT = """📖 Команды

Кнопки
/клава - прислать свежие кнопки
/застрял - если игра зависла

Персонаж
/профиль - кто ты и сколько у тебя всего
/квест - текущее задание сюжета
/ежедневки - ежедневные задания
/пресет 2 - включить пресет номер 2
/съесть Уха - съесть блюдо вне боя
/ключ - осмотреть Ключ Монолита
/реликвии - твои реликвии и сколько за них даст скупщик
/рынок - твои заявки на рынке и купленное

Мир
/озеро, /рудник, /монолит - подойти, если стоишь на клетке
/рыба1 - озера первого кольца (цифра - кольцо)
/руда1 - рудники первого кольца и руда в них
/разломы - открытые разломы
/топ - лучшие игроки

Игроки
/пригласить Ник - позвать в группу (или перешли его сообщение с этой подписью)
/выйти - выйти из группы
/выгнать Ник - убрать из группы
/напасть 2 - напасть на игрока под номером 2 из «Осмотреться»
/передать золото 500 - перешли сообщение игрока с этой подписью (несколько вещей - через запятую)
/заказ - заказы на головы
/гильдия - твоя гильдия
/страж - страж гильдии

/баг текст - сообщить об ошибке"""


@labeler.message(text=["/помощь", "/команды", "/help"])
async def handle_help(message: Message) -> None:
    # Справка не трогает клавиатуру: работает и посреди боя.
    await info_reply.answer(message, HELP_TEXT)


@labeler.message(text=["/профиль", "/profile"])
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
    # На озере и в руднике - кнопки экрана (bot/info_reply.py).
    state_kb = await info_reply.keyboard_for(message.peer_id, message.from_id)
    if state_kb is not None:
        await message.answer(text, keyboard=state_kb)
        return

    # Клавиатуру шлём только если мини-апп настроен — иначе пустая
    # клавиатура затёрла бы уже показанные игроку кнопки города/мира.
    kb = Keyboard(one_time=False, inline=True)
    add_miniapp_button(kb)
    keyboard = kb.get_json() if kb.buttons and kb.buttons[0] else None
    await message.answer(text, keyboard=keyboard)
