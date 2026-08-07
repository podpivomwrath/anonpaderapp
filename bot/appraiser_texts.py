"""Тексты скупщика трофеев (content/npc/appraiser.json, патч 9 блок 3)."""

from bot.vk_media import photo_attachment
from game.combat import display
from game.content_loader import load_npc_texts

APPRAISER = load_npc_texts("appraiser")


def appraiser_attachment() -> str | None:
    photo_id = APPRAISER.get("image")
    return photo_attachment(photo_id) if photo_id else None


def appraiser_intro() -> str:
    return APPRAISER["intro"]


def appraiser_empty() -> str:
    return APPRAISER["empty"]


def appraiser_gear_empty() -> str:
    return APPRAISER["gear_empty"]


def appraiser_sold(gold: int, total: int) -> str:
    """Патч 13, ч.2: сумма сделки + новый баланс единой числовой скобкой."""
    return f"{APPRAISER['sold']} {display.gold_delta_line(gold, total)}"
