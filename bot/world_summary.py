"""Единая сводка локации (ux-patch-5, ux-patch-10): координаты/тип локации/зона
+ описание + HP + уровень + опыт + золото.

Всегда САМОСТОЯТЕЛЬНОЕ сообщение (ux-patch-10, п.1) — не склеивается с текстом
события/боя/флейвора, замыкает цикл действия и несёт кнопки следующего шага.
Leaf-модуль: импортируется и world.py, и combat.py, сам их не импортирует
(без циклов).
"""

import random

from game.combat import balance_config as bc
from game.combat import display
from game.world import grid, location_types
from services import experience_service, vitals_service

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


def location_summary(
    character, stats, rng: random.Random, farm_currency: int, vit_bonus: int = 0
) -> str:
    """Сводка клетки: координаты/тип локации/зона, вариативное описание, HP,
    уровень, шкала опыта, золото (патч 9 блок 3, патч 10 блоки 2/4).

    vit_bonus (патч 11, блок 2) — VIT надетой экипировки, чтобы HP-бар совпадал
    с максимумом, который реально используется в бою."""
    x, y = character.pos_x, character.pos_y
    loc_type = location_types.location_type_at(x, y)
    lo, hi = grid.zone_level_range(grid.chebyshev_distance(x, y))
    zone_line = f"📍 ({x}; {y}) — {loc_type.name} · зона {lo}-{hi} ур."
    description = rng.choice(loc_type.descriptions)
    max_hp = vitals_service.max_hp(character, stats, vit_bonus)
    current_hp = vitals_service.current_hp(character, stats, vit_bonus)
    hp_line = f"❤️ Здоровье: {display.health_bar(current_hp, max_hp)}"
    return (
        f"{zone_line}\n{description}\n\n"
        f"{_SEP}\n"
        f"{hp_line}\n"
        f"⚔️ Уровень: {character.level}\n"
        f"{xp_bar(character.level, character.experience)}\n"
        f"💰 Золото: {farm_currency}\n"
        f"{_SEP}"
    )
