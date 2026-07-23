"""Скупщик трофеев — Тощий Иргал (патч 9, блок 3). Один NPC во всех городах."""

from vkbottle.bot import BotLabeler, Message

from bot.appraiser_texts import appraiser_empty, appraiser_intro, appraiser_sold
from bot.keyboards.appraiser import SELL_ALL_ID, appraiser_keyboard
from bot.keyboards.world import BTN_APPRAISER, city_menu_keyboard
from game.world import grid
from services import onboarding_service as onboarding_svc
from services import trophy_service
from services.db import get_session_factory

labeler = BotLabeler()


@labeler.message(text=[BTN_APPRAISER])
async def open_appraiser(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is None:
            return  # скупщик только в городе
        stock = await trophy_service.get_stock(db, character.id)

    if not stock:
        await message.answer(
            f"{appraiser_intro()}\n\n{appraiser_empty()}", keyboard=city_menu_keyboard()
        )
        return

    lines = "\n".join(
        f"{d.emoji} {d.name} ×{count} — {d.sell_price * count} зол." for d, count in stock
    )
    await message.answer(
        f"{appraiser_intro()}\n\n{lines}", keyboard=appraiser_keyboard(stock)
    )


@labeler.message(payload_contains={"type": "sell_trophies"})
async def sell_trophies(message: Message) -> None:
    payload = message.get_payload_json() or {}
    trophy_id = payload.get("id")
    if not trophy_id:
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if trophy_id == SELL_ALL_ID:
            gold = await trophy_service.sell_all(db, character)
        else:
            gold = await trophy_service.sell_one(db, character, trophy_id)
        await db.commit()

    if gold <= 0:
        await message.answer(appraiser_empty(), keyboard=city_menu_keyboard())
        return
    await message.answer(appraiser_sold(gold), keyboard=city_menu_keyboard())
