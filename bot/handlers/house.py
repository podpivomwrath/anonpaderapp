"""Дом (2026-10-21): кнопка на площади родного города, внутри печь и
алхимический стол. Числа и продажа - game/economy/house_config.py.

Экран дома живёт рядом с кварталами города (bot/handlers/world.py,
_render_city_screen): «← Площадь» и восстановление клавиатуры - общие.
"""

from vkbottle.bot import BotLabeler, Message

from bot.keyboards import world as kb
from bot.world_texts import FOREIGN_NPC_REJECTION
from game.world import grid
from services import onboarding_service as onboarding_svc
from services import screen_service
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра

HOUSE_TEXT = "🏠 Дом\n\nТвои стены в городе. У окна печь, в углу стол с ретортами и склянками."
OVEN_SOON = "🔥 Печь растоплена, но рецептов у тебя пока нет. Кулинария откроется следующим обновлением."
ALCHEMY_SOON = "⚗️ Склянки чистые, но варить пока нечего. Алхимия откроется следующим обновлением."


def house_text() -> str:
    return HOUSE_TEXT


async def _home_character(message: Message):
    """Персонаж у себя в городе и с домом, иначе None (с ответом, если нужно)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
    if character is None or character.creation_state is not None or not character.has_house:
        return None
    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is None:
        return None
    if region != character.region:
        await message.answer(FOREIGN_NPC_REJECTION)
        return None
    return character


@labeler.message(text=[kb.BTN_HOUSE])
async def open_house(message: Message) -> None:
    character = await _home_character(message)
    if character is None:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        await screen_service.set_screen(db, character, "house")
        await db.commit()
    await message.answer(HOUSE_TEXT, keyboard=kb.house_keyboard())


@labeler.message(text=[kb.BTN_OVEN])
async def open_oven(message: Message) -> None:
    if await _home_character(message) is not None:
        await message.answer(OVEN_SOON, keyboard=kb.house_keyboard())


@labeler.message(text=[kb.BTN_ALCHEMY])
async def open_alchemy(message: Message) -> None:
    if await _home_character(message) is not None:
        await message.answer(ALCHEMY_SOON, keyboard=kb.house_keyboard())
