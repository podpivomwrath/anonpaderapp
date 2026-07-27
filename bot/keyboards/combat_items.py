"""Клавиатура списка зелий/эликсиров в бою (патч 16). INLINE — окно
редактируется на месте (патч 13, ч.1)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import ElixirDef


def combat_items_keyboard(stock: list[tuple[ElixirDef, int]]) -> str:
    kb = Keyboard(inline=True)
    for elixir, count in stock:
        label = f"{elixir.emoji} {elixir.name} ×{count}"
        kb.add(
            Text(label, payload={"type": "use_item", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    return kb.get_json()
