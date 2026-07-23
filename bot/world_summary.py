"""Единая сводка локации (ux-patch-5): координаты/зона + описание + шкала опыта.

Показывается и при заходе на клетку, и финальным сообщением после боя. Leaf-
модуль: импортируется и world.py, и combat.py, сам их не импортирует (без циклов).
"""

import random

from game.combat import balance_config as bc
from game.combat import display
from game.world import flavor, grid
from services import experience_service

_SEP = "━━━━━━━━━━━━━━"


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def xp_bar(level: int, experience: int) -> str:
    """Текстовая шкала опыта текущего уровня. На потолке — «МАКС»."""
    if level >= bc.MAX_LEVEL:
        return "✨ Опыт: МАКС"
    need = experience_service.xp_to_next(level)
    ratio = 0.0 if need <= 0 else max(0.0, min(experience / need, 1.0))
    filled = round(ratio * display.BAR_WIDTH)
    bar = display.BAR_FILLED * filled + display.BAR_EMPTY * (display.BAR_WIDTH - filled)
    percent = round(ratio * 100)
    return f"✨ Опыт: {bar} {_thousands(experience)} / {_thousands(need)} ({percent}%)"


def location_summary(character, rng: random.Random, farm_currency: int) -> str:
    """Сводка клетки: координаты/зона, вариативное описание, уровень, шкала опыта,
    золото (патч 9, блок 3)."""
    x, y = character.pos_x, character.pos_y
    lo, hi = grid.zone_level_range(grid.chebyshev_distance(x, y))
    zone_line = f"📍 ({x}; {y}) — зона {lo}-{hi} ур."
    description = flavor.location_line(character.region, rng)
    return (
        f"{zone_line}\n{description}\n\n"
        f"{_SEP}\n"
        f"⚔️ Уровень: {character.level}\n"
        f"{xp_bar(character.level, character.experience)}\n"
        f"💰 Золото: {farm_currency}\n"
        f"{_SEP}"
    )
