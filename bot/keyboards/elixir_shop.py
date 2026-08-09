"""Клавиатура лавки зелий (патч 16). Окно редактируется на месте при покупке
(патч 13, ч.1), как у скупщика трофеев.

Патч 37: лавка — отдельный ЭКРАН (services/screen_service.py), клавиатура
ОБЫЧНАЯ (не inline) и заменяет городскую целиком, [← Назад] последней
кнопкой. Обычная (не inline) клавиатура ограничена 10 рядами × 40 кнопками
(мягче inline-лимита в 6×10) — полный каталог из 10 эликсиров по 2 в ряд
(5 строк) + [← Назад] с запасом укладывается."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import add_miniapp_button
from game.content_loader import ElixirDef
from game.economy import elixir_config as ec

BTN_BACK = "← Назад"


def shop_keyboard(elixirs: list[ElixirDef]) -> str:
    """2 кнопки в ряд + мини-апп + назад последней строкой."""
    kb = Keyboard(one_time=False)
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
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_BACK, payload={"type": "elixir_shop_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
