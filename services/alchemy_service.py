"""Алхимия (2026-10-21): варка зелий на столе в доме.

Работа в доме хранится в персонаже (house_work = "alchemy:<зелье>",
house_work_until) и переживает рестарт бота. Доваривает её фоновый шаг
bot/handlers/house.py::tick_job. Тексты - там же.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import alchemy
from game.economy import alchemy_config as ac
from models import Character
from services import elixir_service, herb_service, wallet_service

PREFIX = "alchemy:"


class AlchemyError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_working(character: Character) -> bool:
    return character.house_work is not None


def brewing(character: Character) -> ac.Recipe | None:
    work = character.house_work or ""
    return ac.RECIPES_BY_ID.get(work[len(PREFIX):]) if work.startswith(PREFIX) else None


def seconds_left(character: Character, now: datetime | None = None) -> int:
    if character.house_work_until is None:
        return 0
    return max(0, round((_aware(character.house_work_until) - (now or _now())).total_seconds()))


async def start(db: AsyncSession, character: Character, elixir_id: str, now: datetime | None = None) -> ac.Recipe:
    """Списать травы и золото и поставить варку."""
    recipe = ac.RECIPES_BY_ID.get(elixir_id)
    if recipe is None or recipe.level > character.alchemy_level:
        raise AlchemyError("Этот рецепт тебе пока не знаком.")
    if is_working(character):
        raise AlchemyError("Стол занят: сначала закончи то, что уже на огне.")
    gold = alchemy.gold_cost(recipe, character.alchemy_level)
    if (await wallet_service.get_wallet(db, character.id)).farm_currency < gold:
        raise AlchemyError(f"Не хватает золота на склянки: нужно {gold}.")
    if not await herb_service.spend(db, character.id, recipe.herbs):
        raise AlchemyError("Не хватает трав.")
    await wallet_service.charge(db, character.id, "farm", gold)
    character.house_work = PREFIX + recipe.elixir_id
    character.house_work_until = (now or _now()) + timedelta(seconds=ac.BREW_SECONDS)
    await db.flush()
    return recipe


def cancel(character: Character) -> ac.Recipe | None:
    """Бросить варку: травы и золото не возвращаются."""
    recipe = brewing(character)
    character.house_work = None
    character.house_work_until = None
    return recipe


@dataclass
class Brewed:
    recipe: ac.Recipe
    amount: int
    xp: int
    level_before: int
    level_after: int
    unlocked: list[ac.Recipe] = field(default_factory=list)


async def finish(db: AsyncSession, character: Character, rng: random.Random) -> Brewed | None:
    recipe = brewing(character)
    character.house_work = None
    character.house_work_until = None
    if recipe is None:
        return None
    level = character.alchemy_level
    amount = recipe.out + (alchemy.bonus_amount(recipe) if rng.random() < alchemy.bonus_chance(level) else 0)
    await elixir_service.grant(db, character.id, recipe.elixir_id, amount)
    xp = alchemy.brew_xp(recipe)
    alchemy.grant_xp(character, xp)
    await db.flush()
    return Brewed(recipe, amount, xp, level, character.alchemy_level,
                  alchemy.unlocked_between(level, character.alchemy_level))


async def due(db: AsyncSession, now: datetime | None = None) -> list[Character]:
    """Персонажи, у которых варка готова. Под FOR UPDATE: шаг не доварит
    одно и то же дважды, если наложится на себя."""
    return list((await db.scalars(
        select(Character).where(
            Character.house_work.like(PREFIX + "%"), Character.house_work_until <= (now or _now()),
        ).with_for_update().execution_options(populate_existing=True)
    )).all())
