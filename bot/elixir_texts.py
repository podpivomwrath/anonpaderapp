"""Тексты лавки зелий (content/npc/elixir_shop.json, патч 16)."""

from game.combat import display
from game.content_loader import load_npc_texts

ELIXIR_SHOP = load_npc_texts("elixir_shop")


def shop_intro() -> str:
    return ELIXIR_SHOP["intro"]


def shop_not_enough_gold() -> str:
    return ELIXIR_SHOP["not_enough_gold"]


def shop_bought(name: str, gold: int, total: int) -> str:
    """Патч 13, ч.2: подтверждение покупки + сумма + новый баланс."""
    return f"{ELIXIR_SHOP['bought']}\n{name}. {display.gold_delta_line(-gold, total)}"
