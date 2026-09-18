"""Чистая логика рыбалки (патч 58): озёра, розыгрыш вида/веса, градация,
обрыв лески, цена, уровень рыбалки, садок.

Без БД и без random.seed() внутри — ровно как game/economy/loot.py: rng всегда
приходит снаружи, чтобы тесты и симулятор (tools/sim_fishing.py) могли гонять
одни и те же функции, которыми играет бот. Запись в БД — services/fishing_service.py.
"""

import random

from game.content_loader import FishDef, LakeDef, load_fish_defs, load_lakes
from game.economy import fishing_config as fc

_fish_defs: dict[str, FishDef] | None = None
_lakes_by_coords: dict[tuple[int, int], LakeDef] | None = None
_lakes_ordered: list[LakeDef] | None = None


def _fish() -> dict[str, FishDef]:
    global _fish_defs
    if _fish_defs is None:
        _fish_defs = {f.id: f for f in load_fish_defs()}
    return _fish_defs


def _lakes() -> dict[tuple[int, int], LakeDef]:
    global _lakes_by_coords, _lakes_ordered
    if _lakes_by_coords is None:
        _lakes_ordered = load_lakes()
        _lakes_by_coords = {(lake.x, lake.y): lake for lake in _lakes_ordered}
    return _lakes_by_coords


def fish_def(fish_id: str) -> FishDef | None:
    return _fish().get(fish_id)


def fish_defs_ordered() -> list[FishDef]:
    """Порядок content/fishing/fish.json — от дешёвых к дорогим."""
    return list(_fish().values())


def all_lakes() -> list[LakeDef]:
    _lakes()
    return list(_lakes_ordered or [])


# --- Клетка ------------------------------------------------------------------

#: (dist_min, dist_max, тир) — те же границы, что world_config.ZONE_TABLE.
#: Тир озера ОБЯЗАН совпадать с тиром своего кольца (проверяется тестом):
#: иначе «сложность озера» и «сложность клетки» разъедутся, и правило PvP
#: (мирные кольца I-II) начало бы противоречить сложности рыбы.
RING_BOUNDS: list[tuple[int, int, int]] = [
    (40, 50, 1), (25, 39, 2), (12, 24, 3), (3, 11, 4), (0, 2, 5),
]


def ring_tier(x: int, y: int) -> int:
    """Тир кольца клетки по расстоянию Чебышёва до Монолита."""
    dist = max(abs(x), abs(y))
    for lo, hi, tier in RING_BOUNDS:
        if lo <= dist <= hi:
            return tier
    return RING_BOUNDS[-1][2]


def lake_at(x: int, y: int) -> LakeDef | None:
    return _lakes().get((x, y))


def is_lake(x: int, y: int) -> bool:
    return (x, y) in _lakes()


def is_safe_lake(x: int, y: int) -> bool:
    """Озёрная клетка, где PvP запрещено (кольца I-II).

    Первые мирные клетки в игре вне городов. Проверяется там же, где городская
    мирная зона — bot/handlers/pvp.py. На клетках БЕЗ озера всегда False:
    мирным делает именно озеро, а не кольцо.
    """
    lake = lake_at(x, y)
    return lake is not None and lake.tier <= fc.PVP_SAFE_MAX_LAKE_TIER


# --- Клёв --------------------------------------------------------------------


def roll_bite(rng: random.Random) -> tuple[float, float]:
    """Розыгрыш поклёвки: (секунд ожидания, бонус к доле веса).

    Поклёвка случается ВСЕГДА — пустых забросов в игре нет. Вопрос только в
    том, сколько ждать, и длинное ожидание намеренно связано с бонусом к весу:
    пауза перестаёт быть пустым временем и становится ожиданием чего-то
    крупного. Риск живёт в обрыве лески, а не в отсутствии клёва.
    """
    roll = rng.random()
    cumulative = 0.0
    for weight, lo, hi, bonus in fc.BITE_MODES:
        cumulative += weight
        if roll < cumulative:
            return rng.uniform(lo, hi), bonus
    _weight, lo, hi, bonus = fc.BITE_MODES[-1]
    return rng.uniform(lo, hi), bonus  # защита от погрешности суммы весов


# --- Вид и вес ---------------------------------------------------------------


def roll_fish_id(rng: random.Random, lake_tier: int) -> str:
    """Какой вид клюнул. Безымянное проверяется ДО пула — оно доступно на
    любом озере и не занимает место в его раскладке."""
    if rng.random() < fc.NAMELESS_CHANCE:
        return fc.NAMELESS_ID
    pool = fc.LAKE_POOLS[lake_tier]
    total = sum(pool.values())
    roll = rng.random() * total
    cumulative = 0.0
    fish_id = None
    for fish_id, weight in pool.items():
        cumulative += weight
        if roll < cumulative:
            return fish_id
    return fish_id  # защита от погрешности с плавающей точкой


def weight_k(fishing_level: int) -> float:
    """Кривизна распределения веса. Падает с уровнем, но асимптотически — к
    WEIGHT_K_FLOOR, никогда не к 1.0: иначе крупная рыба стала бы нормой и
    градации обесценились бы вместе с рекордами."""
    return fc.WEIGHT_K_FLOOR + fc.WEIGHT_K_SPAN * fc.WEIGHT_K_DECAY ** (fishing_level - 1)


def roll_weight(
    rng: random.Random, fish_id: str, fishing_level: int, f_bonus: float = 0.0
) -> tuple[int, float]:
    """(вес в граммах, доля веса f в диапазоне вида).

    f возвращается вместе с весом, а не пересчитывается потом: градация, опыт
    и шанс обрыва обязаны смотреть на ОДНО И ТО ЖЕ число, иначе они разойдутся
    на границах диапазонов.
    """
    lo, hi, _price = fc.FISH_STATS[fish_id]
    fraction = min(rng.random() ** weight_k(fishing_level) + f_bonus, 1.0)
    grams = round(lo + (hi - lo) * fraction)
    return grams, fraction


def grade_for(fraction: float) -> tuple[str, str, float]:
    """(id градации, название, множитель цены) по доле веса."""
    result = fc.GRADES[0]
    for grade in fc.GRADES:
        if fraction >= grade[0]:
            result = grade
    return result[1], result[2], result[3]


def grade_name(grade_id: str) -> str:
    for _threshold, gid, name, _mult in fc.GRADES:
        if gid == grade_id:
            return name
    return grade_id


def grade_multiplier(grade_id: str) -> float:
    for _threshold, gid, _name, mult in fc.GRADES:
        if gid == grade_id:
            return mult
    return 1.0


def fraction_of(fish_id: str, grams: int) -> float:
    """Обратное к roll_weight — доля веса для уже известного экземпляра
    (нужно рекордам и отображению, где хранится только вес)."""
    lo, hi, _price = fc.FISH_STATS[fish_id]
    if hi <= lo:
        return 0.0
    return max(0.0, min((grams - lo) / (hi - lo), 1.0))


# --- Обрыв лески -------------------------------------------------------------


def line_break_reduction(fishing_level: int) -> float:
    """Насколько уровень сбивает шанс обрыва. Затухает и упирается в
    LINE_BREAK_REDUCTION_MAX: иначе глубокое озеро на высоком уровне
    перестаёт сопротивляться вовсе, и рыбалка обгоняет всю остальную
    экономику (измерено симулятором, см. комментарий в конфиге)."""
    return fc.LINE_BREAK_REDUCTION_MAX * (
        1 - fc.LINE_BREAK_REDUCTION_DECAY ** fishing_level
    )


def line_break_chance(lake_tier: int, fishing_level: int, fraction: float) -> float:
    """Мягкий гейт вместо запрета: формально рыбачить можно где угодно, но
    новичок у Монолита рвёт леску почти всегда, а мастер — всё равно часто."""
    chance = (
        fc.LINE_BREAK_BASE[lake_tier]
        - line_break_reduction(fishing_level)
        + fraction * fc.LINE_BREAK_BY_WEIGHT
    )
    return max(fc.LINE_BREAK_MIN, min(chance, fc.LINE_BREAK_MAX))


# --- Цена --------------------------------------------------------------------


def price_of(fish_id: str, grams: int, grade_id: str) -> int:
    """Каталожная цена (то, от чего считаются и скидка Иргала, и наценка
    ивента). Линейна по весу — именно поэтому стак «вид + градация» можно
    хранить одним суммарным весом и считать цену прямо от него."""
    _lo, _hi, per_kg = fc.FISH_STATS[fish_id]
    return max(round(per_kg * grams / 1000 * grade_multiplier(grade_id)), 1)


# --- Уровень рыбалки ---------------------------------------------------------


def xp_to_next(fishing_level: int) -> int:
    """Потолка нет: каждый следующий уровень дороже предыдущего, расти можно
    бесконечно (в отличие от боевого уровня с MAX_LEVEL=60)."""
    return round(fc.FISHING_XP_BASE * fishing_level ** fc.FISHING_XP_EXP)


def catch_xp(fish_id: str, fraction: float, landed: bool = True) -> int:
    """Опыт за экземпляр. Сорвавшаяся рыба даёт долю — иначе низкий уровень на
    сложном озере не ловит НИЧЕГО и при этом не растёт, то есть выбраться из
    ямы нечем."""
    definition = fish_def(fish_id)
    tier = definition.tier if definition else 1
    base = fc.FISHING_TIER_XP.get(tier, 1) * (1 + fc.FISHING_XP_WEIGHT_BONUS * fraction)
    if not landed:
        base *= fc.FISHING_XP_ON_BREAK
    return max(round(base), 1)


def add_fishing_xp(fishing_level: int, fishing_xp: int, gained: int) -> tuple[int, int, int]:
    """(новый уровень, остаток опыта, сколько уровней взято). Потолка нет,
    поэтому цикл ограничен только тем, что xp_to_next растёт быстрее опыта."""
    level, xp, levels = fishing_level, fishing_xp + gained, 0
    while xp >= xp_to_next(level):
        xp -= xp_to_next(level)
        level += 1
        levels += 1
    return level, xp, levels


# --- Садок -------------------------------------------------------------------


def bag_capacity_grams(fishing_level: int) -> int:
    """Вместимость в ГРАММАХ (меряется в килограммах, хранится в граммах —
    единица веса в системе одна). Растёт с уровнем с затуханием: уровень
    бесконечен, а садок — нет."""
    kilos = fc.BAG_BASE_KG + fc.BAG_SPAN_KG * (1 - fc.BAG_DECAY ** fishing_level)
    return round(kilos * 1000)


def format_kg(grams: int) -> str:
    """Единое представление веса в тексте: килограммы с одним знаком."""
    return f"{grams / 1000:.1f} кг".replace(".", ",")
