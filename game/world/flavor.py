"""Атмосферные тексты мира (atmosphere-patch-3): переходы, события.

Все пулы — в content/flavor/*.json, выбор случайный. Пополняется контентом.
Описания клеток карты — см. game/world/location_types.py (патч 10, блок 4).
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

_CONTENT = Path(__file__).resolve().parent.parent.parent / "content" / "flavor"


def _load(name: str) -> dict:
    with (_CONTENT / name).open(encoding="utf-8") as f:
        return json.load(f)


_SYSTEM = _load("system.json")
_SONG = _load("ashen_song.json")
_REMARKS = _load("remarks.json")

# Шанс показать атмосферный фрагмент перед мобом при исследовании (~50%)
EXPLORE_FRAGMENT_CHANCE = 0.5


def travel_line(rng: random.Random) -> str:
    return rng.choice(_SYSTEM["travel"])


def rest_start() -> str:
    return _SYSTEM["rest_start"]


def rest_done() -> str:
    return _SYSTEM["rest_done"]


def death_line() -> str:
    return _SYSTEM["death"]


def respawn_line(city_title: str) -> str:
    return _SYSTEM["respawn"].format(city=city_title)


def levelup_line(level: int, rng: random.Random) -> str:
    return rng.choice(_SYSTEM["levelup"]).format(level=level)


def death_penalty_line(xp: int) -> str:
    return _SYSTEM["death_penalty"].format(xp=xp)


def quest_reward_line(xp: int) -> str:
    return _SYSTEM["quest_reward"].format(xp=xp)


@dataclass
class FlavorPick:
    """Выбранный фрагмент + признак награды (ux-patch-10 п.3: замечания-находки
    больше не бывают чистым флейвором — reward None/"trophy"/"xp")."""

    text: str
    reward: str | None = None


def song_pick(rng: random.Random) -> FlavorPick:
    part = rng.choice(_SONG["parts"])
    return FlavorPick(text=f"{_SONG['label']}\n{part}")


def remark_pick(rng: random.Random) -> FlavorPick:
    entry = rng.choice(_REMARKS["remarks"])
    return FlavorPick(text=f"{_REMARKS['label']} {entry['text']}", reward=entry.get("reward"))


def song_or_remark_pick(rng: random.Random) -> FlavorPick:
    """Гарантированный фрагмент: 50/50 Песнь или замечание (патч 9, блок 1)."""
    if rng.random() < 0.5:
        return song_pick(rng)
    return remark_pick(rng)


def song_line(rng: random.Random) -> str:
    """Гарантированный обрывок Пепельной Песни (без варианта замечания)."""
    return song_pick(rng).text


def remark_line(rng: random.Random) -> str:
    """Гарантированное замечание (без варианта Песни), без учёта награды —
    для мест, где награда не применяется (напр. превью при клике «Исследовать»)."""
    return remark_pick(rng).text


def song_or_remark(rng: random.Random) -> str:
    """Как song_or_remark_pick, но только текст (награда не учитывается)."""
    return song_or_remark_pick(rng).text


def explore_fragment(rng: random.Random) -> str | None:
    """С шансом EXPLORE_FRAGMENT_CHANCE — фрагмент (Песнь или замечание), иначе
    None. Это превью ДО начала исследования — награды здесь не выдаются, даже
    если случайно выпало замечание-находка; настоящая находка с наградой
    происходит позже, в исходе исследования (см. bot/handlers/world.py)."""
    if rng.random() >= EXPLORE_FRAGMENT_CHANCE:
        return None
    return song_or_remark(rng)
