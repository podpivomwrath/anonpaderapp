"""Чистая логика горного дела (патч 59): рудники, время добычи, вид и
градация руды, уровень.

Без БД и без собственного rng — как game/economy/fishing.py. Состояние жил
(сколько руды сейчас в руднике) живёт в БД и принадлежит
services/mining_service.py: это состояние МИРА, общее для всех игроков, а не
свойство контента.
"""

import random

from game.content_loader import MineDef, OreDef, load_mines, load_ore_defs
from game.economy import mining_config as mc
from game.economy.fishing import (  # noqa: F401 - общее правило колец
    RING_BOUNDS,
    ring_tier,
)

_ore_defs: dict[str, OreDef] | None = None
_mines_by_coords: dict[tuple[int, int], MineDef] | None = None
_mines_ordered: list[MineDef] | None = None


def _ores() -> dict[str, OreDef]:
    global _ore_defs
    if _ore_defs is None:
        _ore_defs = {o.id: o for o in load_ore_defs()}
    return _ore_defs


def _mines() -> dict[tuple[int, int], MineDef]:
    global _mines_by_coords, _mines_ordered
    if _mines_by_coords is None:
        _mines_ordered = load_mines()
        _mines_by_coords = {(m.x, m.y): m for m in _mines_ordered}
    return _mines_by_coords


def ore_def(ore_id: str) -> OreDef | None:
    return _ores().get(ore_id)


def ore_defs_ordered() -> list[OreDef]:
    return list(_ores().values())


def all_mines() -> list[MineDef]:
    _mines()
    return list(_mines_ordered or [])


def mine_at(x: int, y: int) -> MineDef | None:
    return _mines().get((x, y))


def mine_by_id(mine_id: str) -> MineDef | None:
    return next((m for m in all_mines() if m.id == mine_id), None)


def is_mine(x: int, y: int) -> bool:
    return (x, y) in _mines()


def is_safe_mine(x: int, y: int) -> bool:
    """Рудник, где PvP запрещено (кольца I-II).

    Правило намеренно то же, что у озёр: «первые два кольца мирные» игрок
    должен знать одно на все ремёсла, а не по отдельному на каждое.
    """
    mine = mine_at(x, y)
    return mine is not None and mine.tier <= mc.PVP_SAFE_MAX_MINE_TIER


# --- Время добычи -------------------------------------------------------------


def time_multiplier(mine_tier: int, mining_level: int) -> float:
    """Во сколько раз добыча длиннее (или короче) базовой.

    Это единственный гейт глубоких рудников: запрета лезть туда нет, но
    новичок у Монолита копает один кусок час с лишним. Уровень штраф срезает,
    а будущая кирка срежет ещё.
    """
    required = mc.MINE_REQUIRED_LEVEL[mine_tier]
    raw = 1.0 + (required - mining_level) * mc.TIME_PENALTY_PER_LEVEL
    return max(mc.TIME_PENALTY_MIN, min(raw, mc.TIME_PENALTY_MAX))


def roll_dig_seconds(
    rng: random.Random, mine_tier: int, mining_level: int, event_vein: bool = False
) -> float:
    """Сколько секунд займёт добыча одного куска."""
    low, high = mc.EVENT_VEIN_SECONDS if event_vein else mc.STATIC_MINE_SECONDS
    return rng.uniform(low, high) * time_multiplier(mine_tier, mining_level)


def format_duration(seconds: float) -> str:
    """Единый вид длительности в текстах: минуты, часы — если перевалило.

    Округление идёт ДО сравнения с порогом: иначе 59.6 минуты показывались как
    «60 мин», а 60.1 — как «1,0 ч», и рядом в одной таблице стояли два разных
    представления одного и того же времени.
    """
    minutes = round(seconds / 60)
    if minutes < 1:
        return f"{round(seconds)} сек"
    if minutes < 60:
        return f"{minutes} мин"
    return f"{minutes / 60:.1f} ч".replace(".", ",")


# --- Вид и градация -----------------------------------------------------------


def pool_tier_for(mine_tier: int, event_vein: bool) -> int:
    """Мелкая жила из исследования беднее рудника того же кольца — иначе
    рудники были бы не нужны вовсе."""
    if not event_vein:
        return mine_tier
    return max(1, mine_tier - mc.EVENT_VEIN_TIER_PENALTY)


def roll_ore_id(rng: random.Random, mine_tier: int, event_vein: bool = False) -> str:
    """Какая руда попалась. Живой камень проверяется ДО пула: он доступен в
    любой выработке и не занимает места в её раскладке."""
    if rng.random() < mc.LIVING_STONE_CHANCE:
        return mc.LIVING_STONE_ID
    pool = mc.MINE_POOLS[pool_tier_for(mine_tier, event_vein)]
    total = sum(pool.values())
    roll = rng.random() * total
    cumulative = 0.0
    ore_id = None
    for ore_id, weight in pool.items():
        cumulative += weight
        if roll < cumulative:
            return ore_id
    return ore_id  # защита от погрешности с плавающей точкой


def grade_k(mine_tier: int, mining_level: int, event_vein: bool = False) -> float:
    """Кривизна броска градации. Меньше — лучше руда."""
    level_mult = mc.GRADE_K_LEVEL_FLOOR + (1 - mc.GRADE_K_LEVEL_FLOOR) * (
        mc.GRADE_K_LEVEL_DECAY ** (mining_level - 1)
    )
    k = mc.MINE_GRADE_K[mine_tier] * level_mult
    if event_vein:
        k *= mc.EVENT_VEIN_GRADE_K_PENALTY
    return k


def roll_grade(
    rng: random.Random, mine_tier: int, mining_level: int, event_vein: bool = False
) -> tuple[str, str]:
    """(id градации, название). Разыгрывается в момент ДОБЫЧИ, а не при спавне
    руды в жиле: жила хранит только количество, иначе игроки выцепляли бы из
    общих рудников легендарное, оставляя другим обычное."""
    roll = rng.random() ** grade_k(mine_tier, mining_level, event_vein)
    result = mc.GRADES[0]
    for grade in mc.GRADES:
        if roll >= grade[0]:
            result = grade
    return result[1], result[2]


def grade_name(grade_id: str) -> str:
    for _threshold, gid, name in mc.GRADES:
        if gid == grade_id:
            return name
    return grade_id


def grade_order(grade_id: str) -> int:
    """Порядковый номер градации — для сортировки инвентаря от лучшей к худшей."""
    for index, (_threshold, gid, _name) in enumerate(mc.GRADES):
        if gid == grade_id:
            return index
    return 0


# --- Уровень ------------------------------------------------------------------


def xp_to_next(mining_level: int) -> int:
    """Потолка нет, каждый следующий уровень дороже — как у рыбалки."""
    return round(mc.MINING_XP_BASE * mining_level ** mc.MINING_XP_EXP)


def dig_xp(ore_id: str, grade_id: str) -> int:
    definition = ore_def(ore_id)
    tier = definition.tier if definition else 1
    base = mc.MINING_TIER_XP.get(tier, 1) * mc.MINING_GRADE_XP_MULT.get(grade_id, 1.0)
    return max(round(base), 1)


def add_mining_xp(mining_level: int, mining_xp: int, gained: int) -> tuple[int, int, int]:
    """(новый уровень, остаток опыта, сколько уровней взято)."""
    level, xp, levels = mining_level, mining_xp + gained, 0
    while xp >= xp_to_next(level):
        xp -= xp_to_next(level)
        level += 1
        levels += 1
    return level, xp, levels
