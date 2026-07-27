"""Клавиатура лавки зелий (патч 16). INLINE — окно редактируется на месте
при покупке (патч 13, ч.1), как у скупщика трофеев.

VK ограничивает inline-клавиатуру 6 рядами И 10 кнопками суммарно (жёстче,
чем обычная reply-клавиатура: 10 рядов × 40 кнопок) — полный каталог из 10
эликсиров уже занимает весь лимит, поэтому кнопку мини-аппа сюда добавить
нельзя (ошибка 911 "too much buttons")."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import ElixirDef
from game.economy import elixir_config as ec


def shop_keyboard(elixirs: list[ElixirDef]) -> str:
    """2 кнопки в ряд, без кнопки мини-аппа (см. лимит выше)."""
    kb = Keyboard(inline=True)
    for idx, elixir in enumerate(elixirs):
        price = ec.ELIXIR_PRICES.get(elixir.id, 0)
        label = f"{elixir.emoji} {elixir.name} — {price} зол."
        kb.add(
            Text(label, payload={"type": "buy_elixir", "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if idx % 2 == 1:
            kb.row()
    if len(elixirs) % 2 == 1:
        kb.row()
    return kb.get_json()
