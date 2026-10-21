"""Алхимия: чистая логика без БД (2026-10-21). Числа - alchemy_config."""

from game.economy import alchemy_config as ac
from game.economy import elixir_config as ec


def xp_to_next(level: int) -> int:
    """0 - потолок."""
    if level >= ac.MAX_LEVEL:
        return 0
    return round(ac.XP_BASE + ac.XP_PER_LEVEL * level ** ac.XP_EXP)


def grant_xp(character, xp: int) -> None:
    if character.alchemy_level >= ac.MAX_LEVEL:
        return
    character.alchemy_xp += xp
    while character.alchemy_level < ac.MAX_LEVEL:
        need = xp_to_next(character.alchemy_level)
        if character.alchemy_xp < need:
            break
        character.alchemy_xp -= need
        character.alchemy_level += 1
    if character.alchemy_level >= ac.MAX_LEVEL:
        character.alchemy_xp = 0


def known(level: int) -> list[ac.Recipe]:
    return [r for r in ac.RECIPES if r.level <= level]


def next_locked(level: int) -> ac.Recipe | None:
    return next((r for r in ac.RECIPES if r.level > level), None)


def unlocked_between(old: int, new: int) -> list[ac.Recipe]:
    return [r for r in ac.RECIPES if old < r.level <= new]


def gold_cost(recipe: ac.Recipe, level: int) -> int:
    return round(recipe.gold * (1 - ac.GOLD_DISCOUNT_PER_10 * (level // 10)))


def bonus_chance(level: int) -> float:
    return ac.BONUS_CHANCE_PER_10 * (level // 10)


def bonus_amount(recipe: ac.Recipe) -> int:
    return ac.BONUS_HEAL if recipe.elixir_id in ec.HEAL_IDS else ac.BONUS_COMBAT


def brew_xp(recipe: ac.Recipe) -> int:
    return ac.BREW_XP_BASE + ac.BREW_XP_PER_LEVEL * recipe.level
