"""Скупщик — Тощий Иргал: трофеи (патч 9, блок 3) + снаряжение (патч 11, блок 2).
Один NPC во всех городах.

Патч 13, ч.1: окно скупщика — ОДНО сообщение, редактируется на месте при
каждой продаже (поштучно), вместо каскада новых сообщений."""

from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message
from bot.appraiser_texts import (
    appraiser_attachment,
    appraiser_empty,
    appraiser_gear_empty,
    appraiser_intro,
    appraiser_sold,
)
from bot.keyboards.appraiser import (
    BTN_SELL_GEAR,
    SELL_ALL_ID,
    appraiser_keyboard,
    no_keyboard,
    sell_gear_keyboard,
)
from bot.keyboards.world import BTN_APPRAISER
from bot.world_texts import FOREIGN_APPRAISER_INTRO_SUFFIX
from game.combat import balance_config as bc
from game.world import grid
from services import daily_service, item_service
from services import onboarding_service as onboarding_svc
from services import trophy_service
from services import wallet_service
from services.db import get_session_factory

labeler = BotLabeler()

_NS = "appraiser"
_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _price_multiplier(character, region: str | None) -> float:
    """Патч 26: скупщик в чужом городе платит FOREIGN_CITY_PRICE_PENALTY."""
    if region is not None and region != character.region:
        return bc.FOREIGN_CITY_PRICE_PENALTY
    return 1.0


def _intro(price_multiplier: float) -> str:
    return appraiser_intro() + (FOREIGN_APPRAISER_INTRO_SUFFIX if price_multiplier < 1.0 else "")


@labeler.message(text=[BTN_APPRAISER])
async def open_appraiser(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # скупщик только в городе
        mult = _price_multiplier(character, region)
        stock = await trophy_service.get_stock(db, character.id)

    if not stock:
        await editable_message.send_or_edit(
            _bot_api, _NS, peer_id,
            f"{_intro(mult)}\n\n{appraiser_empty()}", appraiser_keyboard(stock),
            attachment=appraiser_attachment(),
        )
        return

    lines = "\n".join(
        f"{d.emoji} {d.name} ×{count} — {round(d.sell_price * mult) * count} зол." for d, count in stock
    )
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, f"{_intro(mult)}\n\n{lines}", appraiser_keyboard(stock),
        attachment=appraiser_attachment(),
    )


@labeler.message(payload_contains={"type": "sell_trophies"})
async def sell_trophies(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    trophy_id = payload.get("id")
    if not trophy_id:
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        if trophy_id == SELL_ALL_ID:
            gold = await trophy_service.sell_all(db, character, mult)
        else:
            gold = await trophy_service.sell_one(db, character, trophy_id, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        stock = await trophy_service.get_stock(db, character.id)

    if gold <= 0:
        await editable_message.send_or_edit(
            _bot_api, _NS, peer_id, appraiser_empty(), appraiser_keyboard(stock),
            attachment=appraiser_attachment(),
        )
        return

    if not stock:
        text = f"{appraiser_sold(gold, total)}\n\n{appraiser_empty()}"
    else:
        lines = "\n".join(
            f"{d.emoji} {d.name} ×{count} — {round(d.sell_price * mult) * count} зол." for d, count in stock
        )
        text = f"{appraiser_sold(gold, total)}\n\n{lines}"
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, appraiser_keyboard(stock), attachment=appraiser_attachment(),
    )

    daily_notice = dailies_texts.progress_notice(daily_progress)
    if daily_notice:
        await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)


@labeler.message(text=[BTN_SELL_GEAR])
async def open_sell_gear(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return
        mult = _price_multiplier(character, region)
        items = await item_service.get_inventory(db, character.id)
        sellable = [
            (item, item_service.sell_price(item, mult)) for item, equipped in items if not equipped
        ]

    if not sellable:
        await editable_message.send_or_edit(
            _bot_api, _NS, peer_id, appraiser_gear_empty(), no_keyboard(),
        )
        return

    lines = "\n".join(f"{item.name} — {price} зол." for item, price in sellable)
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, f"🗡️ Продать снаряжение:\n\n{lines}", sell_gear_keyboard(sellable),
    )


@labeler.message(payload_contains={"type": "sell_item"})
async def sell_gear(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    item_id = payload.get("item")
    if not isinstance(item_id, int):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        gold = await item_service.sell_item(db, character, item_id, mult)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        items = await item_service.get_inventory(db, character.id)
        sellable = [
            (item, item_service.sell_price(item, mult)) for item, equipped in items if not equipped
        ]

    if gold <= 0:
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, appraiser_gear_empty(), no_keyboard())
        return

    if not sellable:
        text = f"{appraiser_sold(gold, total)}\n\n{appraiser_gear_empty()}"
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, no_keyboard())
        return

    lines = "\n".join(f"{item.name} — {price} зол." for item, price in sellable)
    text = f"{appraiser_sold(gold, total)}\n\n🗡️ Продать снаряжение:\n\n{lines}"
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, sell_gear_keyboard(sellable))
