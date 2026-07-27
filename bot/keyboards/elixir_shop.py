"""Клавиатура лавки зелий (патч 16). INLINE — окно редактируется на месте
при покупке (патч 13, ч.1), как у скупщика трофеев."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import ElixirDef
from game.economy import elixir_config as ec


def shop_keyboard(elixirs: list[ElixirDef]) -> str:
    kb = Keyboard(inline=True)
    for elixir in elixirs:
        price = ec.ELIXIR_PRICES.get(elixir.id, 0)
        label = f"{elixir.emoji} {elixir.name} — {price} зол."
        kb.add(
            Text(label, payload={"type": "buy_elixir", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()
