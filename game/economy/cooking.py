"""Кулинария: чистая логика без БД (2026-10-21). Числа - cooking_config."""

from game.content_loader import DishDef, load_dish_defs
from game.economy import cooking_config as cc

_defs: dict[str, DishDef] | None = None


def dish_def(dish_id: str) -> DishDef | None:
    global _defs
    if _defs is None:
        _defs = {d.id: d for d in load_dish_defs()}
    return _defs.get(dish_id)


def xp_to_next(level: int) -> int:
    if level >= cc.MAX_LEVEL:
        return 0
    return round(cc.XP_BASE + cc.XP_PER_LEVEL * level ** cc.XP_EXP)


def grant_xp(character, xp: int) -> None:
    if character.cooking_level >= cc.MAX_LEVEL:
        return
    character.cooking_xp += xp
    while character.cooking_level < cc.MAX_LEVEL:
        need = xp_to_next(character.cooking_level)
        if character.cooking_xp < need:
            break
        character.cooking_xp -= need
        character.cooking_level += 1
    if character.cooking_level >= cc.MAX_LEVEL:
        character.cooking_xp = 0


def known(level: int) -> list[cc.Dish]:
    return [d for d in cc.DISHES if d.level <= level]


def next_locked(level: int) -> cc.Dish | None:
    return next((d for d in cc.DISHES if d.level > level), None)


def unlocked_between(old: int, new: int) -> list[cc.Dish]:
    return [d for d in cc.DISHES if old < d.level <= new]


def cook_xp(dish: cc.Dish) -> int:
    return cc.COOK_XP_BASE + cc.COOK_XP_PER_LEVEL * dish.level


def fish_fits(fish_tier: int, dish: cc.Dish) -> bool:
    """Безымянная тварь (6 тир) идёт в блюда 5-го."""
    return fish_tier == dish.fish_tier or (dish.fish_tier == 5 and fish_tier == 6)


def portions(grams: int, dish: cc.Dish) -> int:
    return min(cc.MAX_PORTIONS, grams // cc.PORTION_GRAMS[dish.fish_tier])


def grams_used(n_portions: int, dish: cc.Dish) -> int:
    return n_portions * cc.PORTION_GRAMS[dish.fish_tier]


def food_minutes(level: int) -> int:
    extra = max((m for lvl, m in cc.EXTRA_MINUTES.items() if level >= lvl), default=0)
    return cc.FOOD_MINUTES + extra


def buff_values(dish: cc.Dish, grade: str) -> dict[str, float]:
    mult = cc.GRADE_MULT.get(grade, 1.0)
    return {k: round(v * mult, 4) for k, v in dish.buff.items()}


def buff_text(dish: cc.Dish, grade: str) -> str:
    return ", ".join(
        f"+{round(v * 100)}% {cc.BUFF_TITLES[k]}" for k, v in buff_values(dish, grade).items()
    )
