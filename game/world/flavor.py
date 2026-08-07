"""Атмосферные тексты мира (atmosphere-patch-3): переходы, события.

Все пулы — в content/flavor/*.json, выбор случайный. Пополняется контентом.
Описания клеток карты — см. game/world/location_types.py (патч 10, блок 4).
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

from game.combat import balance_config as bc
from game.combat import display

_CONTENT = Path(__file__).resolve().parent.parent.parent / "content" / "flavor"


def _load(name: str) -> dict:
    with (_CONTENT / name).open(encoding="utf-8") as f:
        return json.load(f)


_SYSTEM = _load("system.json")
_SONG = _load("ashen_song.json")
_REMARKS = _load("remarks.json")
_WORLD_EDGE = _load("world_edge.json")

# Шанс показать атмосферный фрагмент перед мобом при исследовании (~50%)
EXPLORE_FRAGMENT_CHANCE = 0.5


def travel_line(rng: random.Random) -> str:
    return rng.choice(_SYSTEM["travel"])


def world_edge_line(rng: random.Random) -> str:
    """Патч 31, п.7: попытка шагнуть за границу карты (-50..50) — лорный
    отказ вместо тихого игнора, позиция игрока не меняется."""
    return rng.choice(_WORLD_EDGE["lines"])


def rest_start() -> str:
    return _SYSTEM["rest_start"]


def rest_done() -> str:
    return _SYSTEM["rest_done"]


def death_line() -> str:
    return _SYSTEM["death"]


def respawn_line(city_title: str) -> str:
    return _SYSTEM["respawn"].format(city=city_title)


def levelup_line(level: int, rng: random.Random) -> str:
    """Патч 25, п.2: левелап лечит до полного HP — отражаем в тексте."""
    return rng.choice(_SYSTEM["levelup"]).format(level=level) + "\n(Здоровье восстановлено: 100%)"


def death_penalty_line(xp: int) -> str:
    """Штраф опыта: доля добавлена патчем 13, ч.2 (бок о бок с абсолютным числом)."""
    return f"{_SYSTEM['death_penalty']} {display.xp_penalty_line(xp, bc.DEATH_XP_PENALTY)}"


def quest_reward_line(xp: int) -> str:
    return _SYSTEM["quest_reward"].format(xp=xp)


def song_part_count() -> int:
    """Патч 25, п.6: сколько всего обрывков Пепельной Песни (для прогресса
    сбора services/song_service.py)."""
    return len(_SONG["parts"])


def song_parts() -> list[str]:
    """Все 10 текстов по порядку (патч 25, п.6: прогресс сбора в мини-аппе)."""
    return list(_SONG["parts"])


def song_pick(rng: random.Random) -> tuple[int, str]:
    """(индекс обрывка, готовый текст) — индекс нужен для трекинга сбора
    (патч 25, п.6), сам выбор остаётся случайным флейвором, как раньше."""
    part = rng.choice(_SONG["parts"])
    index = _SONG["parts"].index(part)
    return index, f"{_SONG['label']}\n{part}"


def remark_pick(rng: random.Random) -> str:
    """Чистое наблюдение без находки (патч 13, ч.3) — награды тут не бывает
    в принципе, пул используется только как текст ожидания исследования."""
    entry = rng.choice(_REMARKS["remarks"])
    return f"{_REMARKS['label']} {entry}"


@dataclass
class ExploreFragment:
    text: str
    song_index: int | None = None  # None — это было замечание, не обрывок Песни


def song_or_remark(rng: random.Random) -> ExploreFragment:
    """50/50 Песнь или замечание (патч 9, блок 1)."""
    if rng.random() < 0.5:
        index, text = song_pick(rng)
        return ExploreFragment(text=text, song_index=index)
    return ExploreFragment(text=remark_pick(rng))


def explore_fragment(rng: random.Random) -> ExploreFragment | None:
    """С шансом EXPLORE_FRAGMENT_CHANCE — фрагмент (Песнь или замечание), иначе
    None. Текст ожидания перед исходом исследования (патч 13, ч.3: единственное
    место, где этот флейвор теперь встречается — самостоятельным исходом он
    больше не бывает)."""
    if rng.random() >= EXPLORE_FRAGMENT_CHANCE:
        return None
    return song_or_remark(rng)
