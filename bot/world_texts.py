"""Тексты мира: наставники городов (content/npc/mentors.json)."""

from game.content_loader import load_npc_texts

MENTORS = load_npc_texts("mentors")


def mentor_intro(region: str) -> str:
    return MENTORS[region]["intro"]


def mentor_praise(region: str) -> str:
    return MENTORS[region]["praise"]


def mentor_name(region: str) -> str:
    return MENTORS[region]["name"]
