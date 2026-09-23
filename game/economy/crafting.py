"""Чистая логика крафта (патч 72): розыгрыш статов, эффективность, цены.

Без БД и без random.seed() внутри — rng всегда приходит снаружи, ровно как в
game/economy/fishing.py и mining.py. Запись в БД — services/craft_service.py.

Главная мысль системы: выбор специализации НЕ задаёт раскладку статов, он
задаёт предрасположенность. Бюджет очков раздаётся порциями, каждая летит в
стат, выбранный по весам специализации. Поэтому два одинаково скованных
предмета всё равно разные, и есть ради чего перековывать.
"""

import random

from game.content_loader import CraftRecipeDef, load_craft_recipes
from game.economy import craft_config as cc

_recipes: dict[str, CraftRecipeDef] | None = None


def _all() -> dict[str, CraftRecipeDef]:
    global _recipes
    if _recipes is None:
        _recipes = load_craft_recipes()
    return _recipes


def recipe_for(source_id: str) -> CraftRecipeDef | None:
    return _all().get(source_id)


def is_craftable(source_id: str | None) -> bool:
    return source_id is not None and source_id in _all()


def output_name(source_id: str, spec: str) -> str | None:
    recipe = recipe_for(source_id)
    if recipe is None or spec not in recipe.outputs:
        return None
    return recipe.outputs[spec].name


# --- Веса ----------------------------------------------------------------------


def focus_for_grade(grade_id: str) -> float:
    return cc.GRADE_FOCUS.get(grade_id, cc.GRADE_FOCUS_DEFAULT)


def resolve_weights(
    weights: dict[str, float], primary_stat: str, focus: float = 1.0
) -> dict[str, float]:
    """Веса специализации → веса по РЕАЛЬНЫМ статам.

    Делает две вещи разом:
      - резолвит "primary" в str/agi/int по классу владельца (тот же приём,
        что item_config.SLOT_STAT_SPLITS);
      - заостряет распределение возведением в степень focus.

    Заострение применяется ПОСЛЕ резолва: иначе у класса, чей основной стат
    совпадает с профильным статом специализации, два веса сложились бы уже
    после возведения в степень и дали бы другой результат.
    """
    resolved: dict[str, float] = {}
    for key, weight in weights.items():
        stat = primary_stat if key == "primary" else key
        resolved[stat] = resolved.get(stat, 0.0) + weight
    return {stat: weight ** focus for stat, weight in resolved.items()}


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values())
    roll = rng.random() * total
    cumulative = 0.0
    stat = None
    for stat, weight in weights.items():
        cumulative += weight
        if roll < cumulative:
            return stat
    return stat  # защита от погрешности с плавающей точкой


# --- Бюджет и эффективность ----------------------------------------------------


def craft_power(source_power: int) -> int:
    """Бюджет очков ДО множителя эффективности."""
    return round(source_power * cc.CRAFT_POWER_MULT)


def apply_efficiency(power: int, efficiency: int) -> int:
    """Эффективность — множитель к СУММЕ очков, а не к отдельным статам.

    Отсюда важное свойство: поднятие процента пересчитывает тот же самый
    ролл, не трогая раскладку. Игрок, которому повезло с распределением, не
    теряет удачу при улучшении.
    """
    return max(round(power * efficiency / 100), 1)


# --- Розыгрыш ------------------------------------------------------------------


def _split(rng: random.Random, total: int, parts: int) -> list[int]:
    """Делит total на parts СЛУЧАЙНЫХ слагаемых (сумма точная).

    Равные доли выдавали бы механику наружу: при 58 очках на 6 порций все
    статы получались кратными десяти — 9, 10, 19, 29. Случайные разрезы дают
    обычные на вид числа и заодно добавляют разброса сверх самого выбора
    статов.
    """
    if parts <= 1:
        return [total]
    cuts = sorted(rng.randint(0, total) for _ in range(parts - 1))
    bounds = [0, *cuts, total]
    return [bounds[i + 1] - bounds[i] for i in range(parts)]


def roll_stats(
    rng: random.Random,
    weights: dict[str, float],
    power: int,
    primary_stat: str,
    focus: float = 1.0,
    chunks: int = cc.ROLL_CHUNKS,
) -> dict[str, int]:
    """Раздаёт power очков порциями по весам. Пустые статы не возвращаются.

    Порции, а не поочковая раздача: при 58 очках по одному распределение
    почти всегда совпало бы с весами, и все предметы одной специализации
    стали бы одинаковыми. Разброс живёт в том, что бросков мало.
    """
    resolved = resolve_weights(weights, primary_stat, focus)
    if power <= 0 or not resolved:
        return {}

    chunks = max(1, min(chunks, power))
    sizes = _split(rng, power, chunks)

    result: dict[str, int] = {}
    for size in sizes:
        stat = _pick(rng, resolved)
        result[stat] = result.get(stat, 0) + size
    return {stat: amount for stat, amount in result.items() if amount > 0}


def roll_crafted_stats(
    rng: random.Random, spec: str, source_power: int, primary_stat: str,
    ore_tier: int, ore_grade: str,
) -> tuple[dict[str, int], int]:
    """(БАЗОВЫЙ ролл на 100%, стартовая эффективность).

    Ролл всегда разыгрывается на стопроцентном бюджете и хранится таким же.
    Проценты накладываются поверх через stats_at_efficiency. Иначе подъём по
    ступеням 80→90→...→120 был бы цепочкой умножений с округлением на каждом
    шаге, и предмет, поднятый по лестнице, отличался бы от скованного сразу
    на 120 — при одинаковой удаче в ролле.
    """
    efficiency = cc.craft_efficiency_for(ore_tier)
    base = roll_stats(
        rng, cc.SPEC_WEIGHTS[spec], craft_power(source_power), primary_stat,
        focus_for_grade(ore_grade),
    )
    return base, efficiency


def roll_boss_item_stats(
    rng: random.Random, power: int, primary_stat: str
) -> dict[str, int]:
    """Раскладка для предмета, выпавшего с босса.

    Раньше все 100% уходили в основной стат класса. Теперь раскладка
    случайная: боссовая вещь — сырьё для крафта, но носить её можно, и два
    скальпеля не должны быть одинаковыми.
    """
    return roll_stats(rng, cc.BOSS_ITEM_WEIGHTS, power, primary_stat)


def stats_at_efficiency(base_stats: dict[str, int], efficiency: int) -> dict[str, int]:
    """Базовый ролл (100%) → статы на текущей эффективности.

    Единственная точка, где проценты превращаются в числа: и при ковке, и при
    каждом подъёме ступени. Поэтому результат зависит ТОЛЬКО от базового
    ролла и текущего процента, а не от того, какой дорогой игрок до него
    дошёл.
    """
    return {
        stat: max(round(amount * efficiency / 100), 1)
        for stat, amount in base_stats.items()
        if amount > 0
    }


# --- Эффективность и инструменты ------------------------------------------------


def tool_ceiling_for(ore_tier: int) -> int | None:
    """До какой эффективности качает инструмент из руды этого тира."""
    return cc.TOOL_CEILING_BY_ORE_TIER.get(ore_tier)


def next_efficiency(current: int) -> int | None:
    """Следующая ступень, либо None — если уже потолок системы."""
    nxt = current + cc.EFFICIENCY_STEP
    return nxt if nxt <= cc.EFFICIENCY_MAX else None


def can_upgrade_with(current: int, tool_ceiling: int) -> bool:
    """Инструмент с потолком НИЖЕ следующей ступени бесполезен.

    Обратное разрешено: дорогим инструментом можно закрыть дешёвую ступень.
    Расточительно, но запрещать игроку тратить своё незачем.
    """
    nxt = next_efficiency(current)
    return nxt is not None and tool_ceiling >= nxt
