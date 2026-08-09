"""Клавиатура списка зелий/эликсиров в бою (патч 16). INLINE — окно
редактируется на месте (патч 13, ч.1)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import ElixirDef


def combat_items_keyboard(stock: list[tuple[ElixirDef, int]]) -> str:
    """2 кнопки в ряд — при полном наборе (10 видов зелий) 1-в-ряд упирается
    в лимит VK на число рядов клавиатуры (ошибка 911 "too much rows").
    Патч 35, аудит: список ограничен фиксированным контент-каталогом
    (content/items/elixirs.json), а не накопительным инвентарём — не растёт
    от игровых действий игрока, как гир у скупщика. Безопасно, пока каталог
    не перевалит за ~18 видов (9 рядов×2); при таком росте — та же
    группировка/пагинация, что и в bot/keyboards/appraiser.py."""
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
