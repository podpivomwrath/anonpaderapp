"""Тексты лавки зелий (content/npc/elixir_shop.json, патч 16)."""

from bot.vk_media import photo_attachment
from game.combat import display
from game.content_loader import load_npc_texts

ELIXIR_SHOP = load_npc_texts("elixir_shop")


def shop_attachment() -> str | None:
    photo_id = ELIXIR_SHOP.get("image")
    return photo_attachment(photo_id) if photo_id else None


def shop_intro() -> str:
    return ELIXIR_SHOP["intro"]


def shop_not_enough_gold() -> str:
    return ELIXIR_SHOP["not_enough_gold"]


def shop_bought_bulk(name: str, qty: int, gold_spent: int, total_gold: int, new_count: int) -> str:
    """Патч 39, ч.4: подтверждение покупки нескольких штук разом — сумма,
    новый баланс, новое количество в сумке."""
    return (
        f"{ELIXIR_SHOP['bought']}\n{name} ×{qty}. {display.gold_delta_line(-gold_spent, total_gold)}\n"
        f"В сумке теперь: {new_count}."
    )
