"""Тексты скупщика трофеев (content/npc/appraiser.json, патч 9 блок 3)."""

from game.content_loader import load_npc_texts

APPRAISER = load_npc_texts("appraiser")


def appraiser_intro() -> str:
    return APPRAISER["intro"]


def appraiser_empty() -> str:
    return APPRAISER["empty"]


def appraiser_sold(gold: int) -> str:
    return APPRAISER["sold"].format(gold=gold)
