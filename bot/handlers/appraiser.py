"""Скупщик — Тощий Иргал: трофеи (патч 9, блок 3) + снаряжение (патч 11, блок 2).
Один NPC во всех городах."""

from vkbottle.bot import BotLabeler, Message

from bot.appraiser_texts import (
    appraiser_empty,
    appraiser_gear_empty,
    appraiser_intro,
    appraiser_sold,
)
from bot.keyboards.appraiser import (
    BTN_SELL_GEAR,
    SELL_ALL_ID,
    appraiser_keyboard,
    sell_gear_keyboard,
)
from bot.keyboards.world import BTN_APPRAISER, city_menu_keyboard
from game.world import grid
from services import item_service
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
            f"{appraiser_intro()}\n\n{appraiser_empty()}", keyboard=appraiser_keyboard(stock)
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
        await message.answer(appraiser_empty(), keyboard=city_menu_keyboard(character))
        return
    await message.answer(appraiser_sold(gold), keyboard=city_menu_keyboard(character))


@labeler.message(text=[BTN_SELL_GEAR])
async def open_sell_gear(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is None:
            return
        items = await item_service.get_inventory(db, character.id)
        sellable = [(item, item_service.sell_price(item)) for item, equipped in items if not equipped]

    if not sellable:
        await message.answer(appraiser_gear_empty(), keyboard=city_menu_keyboard(character))
        return

    lines = "\n".join(f"{item.name} — {price} зол." for item, price in sellable)
    await message.answer(
        f"🗡️ Продать снаряжение:\n\n{lines}", keyboard=sell_gear_keyboard(sellable)
    )


@labeler.message(payload_contains={"type": "sell_item"})
async def sell_gear(message: Message) -> None:
    payload = message.get_payload_json() or {}
    item_id = payload.get("item")
    if not isinstance(item_id, int):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        gold = await item_service.sell_item(db, character, item_id)
        await db.commit()

    if gold <= 0:
        await message.answer(appraiser_gear_empty(), keyboard=city_menu_keyboard(character))
        return
    await message.answer(appraiser_sold(gold), keyboard=city_menu_keyboard(character))
