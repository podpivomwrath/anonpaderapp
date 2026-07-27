"""Клавиатура списка зелий/эликсиров в бою (патч 16). INLINE — окно
редактируется на месте (патч 13, ч.1)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import ElixirDef


def combat_items_keyboard(stock: list[tuple[ElixirDef, int]]) -> str:
    """2 кнопки в ряд — при полном наборе (10 видов зелий) 1-в-ряд упирается
    в лимит VK на число рядов клавиатуры (ошибка 911 "too much rows")."""
    kb = Keyboard(inline=True)
    for idx, (elixir, count) in enumerate(stock):
        label = f"{elixir.emoji} {elixir.name} ×{count}"
        kb.add(
            Text(label, payload={"type": "use_item", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if idx % 2 == 1:
            kb.row()
    if len(stock) % 2 == 1:
        kb.row()
    return kb.get_json()
