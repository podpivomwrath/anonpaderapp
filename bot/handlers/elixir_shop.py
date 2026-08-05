"""Лавка зелий — Матушка Синель (патч 16). Один NPC во всех городах.

Окно — ОДНО сообщение, редактируется на месте при покупке (патч 13, ч.1),
как у скупщика трофеев."""

from vkbottle.bot import BotLabeler, Message

from bot import editable_message
from bot.elixir_texts import shop_bought, shop_intro, shop_not_enough_gold
from bot.world_texts import FOREIGN_NPC_REJECTION
from bot.keyboards.elixir_shop import shop_keyboard
from bot.keyboards.world import BTN_ELIXIR_SHOP
from game.world import grid
from services import elixir_service
from services import onboarding_service as onboarding_svc
from services import wallet_service
from services.db import get_session_factory
from services.wallet_service import NotEnoughCurrency

labeler = BotLabeler()

_NS = "elixir_shop"
_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def _owned_counts(db, character_id: int) -> dict[str, int]:
    stock = await elixir_service.get_stock(db, character_id)
    return {d.id: count for d, count in stock}


def _catalog_text(counts: dict[str, int]) -> str:
    lines = [shop_intro(), ""]
    for elixir in elixir_service.elixir_defs_ordered():
        owned = counts.get(elixir.id, 0)
        owned_suffix = f" (у тебя: {owned})" if owned else ""
        price = elixir_service.price(elixir.id)
        lines.append(f"{elixir.emoji} {elixir.name} — {price} зол.{owned_suffix}\n{elixir.description}")
    return "\n\n".join(lines)


@labeler.message(text=[BTN_ELIXIR_SHOP])
async def open_shop(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # лавка только в городе
        if region != character.region:
            await message.answer(FOREIGN_NPC_REJECTION)  # патч 26: чужой город
            return
        counts = await _owned_counts(db, character.id)

    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, _catalog_text(counts),
        shop_keyboard(elixir_service.elixir_defs_ordered()),
    )


@labeler.message(payload_contains={"type": "buy_elixir"})
async def buy_elixir(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    elixir_id = payload.get("id")
    elixir = elixir_service.elixir_def(elixir_id) if isinstance(elixir_id, str) else None
    if elixir is None:
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            await elixir_service.buy(db, character, elixir_id)
        except NotEnoughCurrency:
            counts = await _owned_counts(db, character.id)
            text = f"{shop_not_enough_gold()}\n\n{_catalog_text(counts)}"
            await editable_message.send_or_edit(
                _bot_api, _NS, peer_id, text, shop_keyboard(elixir_service.elixir_defs_ordered())
            )
            return
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        counts = await _owned_counts(db, character.id)

    confirm = shop_bought(elixir.name, elixir_service.price(elixir_id), total)
    text = f"{confirm}\n\n{_catalog_text(counts)}"
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, shop_keyboard(elixir_service.elixir_defs_ordered())
    )
