"""Атмосферные тексты мира (atmosphere-patch-3): переходы, локации, события.

Все пулы — в content/flavor/*.json, выбор случайный. Пополняется контентом.
"""

import json
import random
from pathlib import Path

_CONTENT = Path(__file__).resolve().parent.parent.parent / "content" / "flavor"


def _load(name: str) -> dict:
    with (_CONTENT / name).open(encoding="utf-8") as f:
        return json.load(f)


_SYSTEM = _load("system.json")
_LOCATIONS = _load("locations.json")
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


def location_line(region: str, rng: random.Random) -> str:
    """Случайное описание клетки: общий пепельный тон + региональная окраска."""
    pool = list(_LOCATIONS.get("common", []))
    pool += _LOCATIONS.get(region, [])
    return rng.choice(pool) if pool else ""


def song_line(rng: random.Random) -> str:
    """Гарантированный обрывок Пепельной Песни (без варианта замечания)."""
    part = rng.choice(_SONG["parts"])
    return f"{_SONG['label']}\n{part}"


def remark_line(rng: random.Random) -> str:
    """Гарантированное замечание (без варианта Песни)."""
    remark = rng.choice(_REMARKS["remarks"])
    return f"{_REMARKS['label']} {remark}"


def song_or_remark(rng: random.Random) -> str:
    """Гарантированный фрагмент: 50/50 Песнь или замечание (патч 9, блок 1)."""
    if rng.random() < 0.5:
        return song_line(rng)
    return remark_line(rng)


def explore_fragment(rng: random.Random) -> str | None:
    """С шансом EXPLORE_FRAGMENT_CHANCE — фрагмент (Песнь или замечание), иначе None."""
    if rng.random() >= EXPLORE_FRAGMENT_CHANCE:
        return None
    return song_or_remark(rng)
