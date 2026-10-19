"""Турбоишак: чистая логика без БД - клетки, шанс поимки, проверка имени.
Числа - game/economy/turbo_config.py, запись - services/turbo_ishak_service.py."""

import random
import re
from functools import cache
from datetime import datetime, timedelta, timezone

from game.economy import turbo_config as tc
from game.world import grid
from game.world import world_boss

MSK = timezone(timedelta(hours=3))

_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё]+(?:[ -][A-Za-zА-Яа-яЁё]+)*$")


def day_key(now: datetime) -> str:
    return now.astimezone(MSK).strftime("%Y-%m-%d")


def plan_spawn(now: datetime, rng: random.Random) -> datetime | None:
    """Случайный момент в окне сегодняшнего дня (по Москве), не раньше
    сейчас. None - окно уже кончилось, сегодня ишака не будет."""
    local = now.astimezone(MSK)
    start = local.replace(hour=tc.SPAWN_WINDOW_MSK[0], minute=0, second=0, microsecond=0)
    end = local.replace(hour=tc.SPAWN_WINDOW_MSK[1], minute=0, second=0, microsecond=0)
    start = max(start, local)
    if start >= end:
        return None
    moment = start + timedelta(seconds=rng.uniform(0, (end - start).total_seconds()))
    return moment.astimezone(timezone.utc)


@cache
def free_cells() -> list[tuple[int, int]]:
    """Вся карта, кроме Монолита, городов, озёр и рудников - как у мирового
    босса: у тех клеток свои кнопки, ишак среди них потерялся бы."""
    return [c for c in grid.all_cells() if c != (0, 0) and world_boss._cell_is_free(*c)]


def pick_cell(rng: random.Random, avoid: tuple[int, int] | None = None) -> tuple[int, int]:
    """Любая свободная клетка карты - он может перескочить и через полкарты."""
    cells = [c for c in free_cells() if c != avoid]
    return rng.choice(cells)


def next_move_delay(rng: random.Random) -> float:
    return rng.uniform(*tc.MOVE_SECONDS)


def catch_chance(stat: str, stats: dict[str, int]) -> float:
    """stats - итоговые статы с экипировкой. Чем больше доля основного стата,
    тем выше шанс, но не выше CATCH_MAX: сильный не забирает ишака гарантированно."""
    total = sum(max(v, 0) for v in stats.values()) or 1
    share = max(stats.get(stat, 0), 0) / total
    chance = tc.CATCH_BASE + tc.CATCH_SLOPE * (share - 0.2)
    return max(tc.CATCH_MIN, min(tc.CATCH_MAX, chance))


def clean_name(raw) -> str:
    return " ".join(raw.split()) if isinstance(raw, str) else ""


def name_error(name: str) -> str | None:
    """Формат имени (мат проверяет сервис). None - имя годится."""
    if not tc.NAME_MIN <= len(name) <= tc.NAME_MAX:
        return f"Имя - от {tc.NAME_MIN} до {tc.NAME_MAX} букв."
    if not _NAME_RE.match(name):
        return "В имени - только буквы, пробел и дефис."
    return None
