"""Кулинария (2026-10-21): готовка в печи, блюда в инвентаре, бафф от еды.

Готовка - та же «работа в доме», что варка (house_work = "cook:<блюдо>:
<градация>:<порций>"): не выпускает из дома, доготавливается фоновым шагом
bot/handlers/house.py::tick_job. Бафф лежит в персонаже (food_*) и читается
синхронно - его зовут из боя и наград без лишних запросов.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import DishDef, FishDef
from game.economy import cooking
from game.economy import cooking_config as cc
from game.economy import fishing
from models import Character, CharacterFish, CharacterFood
from services import herb_service, wallet_service

PREFIX = "cook:"


class CookingError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Бафф ---------------------------------------------------------------------


def active(character: Character, now: datetime | None = None) -> tuple[cc.Dish, str] | None:
    if not character.food_dish or character.food_until is None:
        return None
    if _aware(character.food_until) <= (now or _now()):
        return None
    dish = cc.DISHES_BY_ID.get(character.food_dish)
    return (dish, character.food_grade or "common") if dish else None


def buff(character: Character, now: datetime | None = None) -> dict[str, float]:
    found = active(character, now)
    if not found:
        return {}
    # Пряности (2026-10-23): заряд при еде делает бафф сильнее.
    boost = 1.0 + (getattr(character, "food_boost", 0.0) or 0.0)
    return {k: round(v * boost, 4) for k, v in cooking.buff_values(*found).items()}


def combat_modifiers(character: Character) -> dict[str, float]:
    """Часть баффа, которая работает в бою (урон, защита, здоровье)."""
    return {k: v for k, v in buff(character).items()
            if k in ("damage_bonus", "incoming_damage_reduction", "max_hp_bonus")}


def hp_mult(character: Character) -> float:
    return 1.0 + buff(character).get("max_hp_bonus", 0.0)


def xp_mult(character: Character) -> float:
    return 1.0 + buff(character).get("xp_bonus", 0.0)


def relic_bonus(character: Character) -> float:
    return buff(character).get("relic_bonus", 0.0)


def minutes_left(character: Character, now: datetime | None = None) -> int:
    if active(character, now) is None:
        return 0
    return max(1, round((_aware(character.food_until) - (now or _now())).total_seconds() / 60))


# --- Готовка ------------------------------------------------------------------


@dataclass
class FishOption:
    fish: FishDef
    grade: str
    grams: int
    portions: int


async def fish_options(db: AsyncSession, character_id: int, dish: cc.Dish) -> list[FishOption]:
    """Стопки рыбы, из которых выйдет хоть одна порция: лучшая градация и
    самая тяжёлая стопка - первыми."""
    rows = (await db.scalars(select(CharacterFish).where(
        CharacterFish.character_id == character_id, CharacterFish.total_grams > 0,
    ))).all()
    order = {g: i for i, g in enumerate(cc.GRADE_ORDER)}
    out = []
    for r in rows:
        fish = fishing.fish_def(r.fish_id)
        if fish is None or not cooking.fish_fits(fish.tier, dish):
            continue
        n = cooking.portions(r.total_grams, dish)
        if n >= 1:
            out.append(FishOption(fish, r.grade, r.total_grams, n))
    out.sort(key=lambda o: (order.get(o.grade, 9), -o.grams))
    return out


def cooking_now(character: Character) -> tuple[cc.Dish, str, int] | None:
    work = character.house_work or ""
    if not work.startswith(PREFIX):
        return None
    try:
        dish_id, grade, n = work[len(PREFIX):].split(":")
        return cc.DISHES_BY_ID[dish_id], grade, int(n)
    except (KeyError, ValueError):
        return None


async def start(
    db: AsyncSession, character: Character, dish_id: str, fish_id: str, grade: str, now: datetime | None = None,
) -> tuple[cc.Dish, int]:
    dish = cc.DISHES_BY_ID.get(dish_id)
    if dish is None or dish.level > character.cooking_level:
        raise CookingError("Этот рецепт тебе пока не знаком.")
    if character.house_work is not None:
        raise CookingError("Печь занята: сначала закончи то, что уже на огне.")
    fish = fishing.fish_def(fish_id)
    if fish is None or not cooking.fish_fits(fish.tier, dish):
        raise CookingError("Эта рыба сюда не подходит.")
    row = await db.scalar(select(CharacterFish).where(
        CharacterFish.character_id == character.id, CharacterFish.fish_id == fish_id, CharacterFish.grade == grade,
    ).with_for_update().execution_options(populate_existing=True))
    n = cooking.portions(row.total_grams, dish) if row is not None else 0
    if n < 1:
        raise CookingError("Этой рыбы не хватит даже на порцию.")
    if (await wallet_service.get_wallet(db, character.id)).farm_currency < dish.gold:
        raise CookingError(f"Не хватает золота на соль и специи: нужно {dish.gold}.")
    if dish.herb and not await herb_service.spend(db, character.id, {dish.herb: 1}):
        raise CookingError("Не хватает травы.")
    row.total_grams -= cooking.grams_used(n, dish)
    await wallet_service.charge(db, character.id, "farm", dish.gold)
    character.house_work = f"{PREFIX}{dish.dish_id}:{grade}:{n}"
    character.house_work_until = (now or _now()) + timedelta(seconds=cc.COOK_SECONDS)
    await db.flush()
    return dish, n


@dataclass
class Cooked:
    dish: cc.Dish
    grade: str
    portions: int
    xp: int
    level_before: int
    level_after: int
    unlocked: list[cc.Dish] = field(default_factory=list)


async def finish(db: AsyncSession, character: Character) -> Cooked | None:
    found = cooking_now(character)
    character.house_work = None
    character.house_work_until = None
    if found is None:
        return None
    dish, grade, n = found
    # Котелок (2026-10-23): шанс лишней порции.
    import random

    from game.economy import craft_gear
    from services import craft_gear_service

    pot = await craft_gear_service.tier(db, character.id, "pot")
    if pot and random.random() < craft_gear.pot_extra_chance(pot):
        n += 1
    from services import master_recipe_service

    n *= master_recipe_service.ring_mult(character)
    await add_food(db, character.id, dish.dish_id, grade, n)
    level = character.cooking_level
    xp = cooking.cook_xp(dish)
    cooking.grant_xp(character, xp)
    await db.flush()
    return Cooked(dish, grade, n, xp, level, character.cooking_level,
                  cooking.unlocked_between(level, character.cooking_level))


async def due(db: AsyncSession, now: datetime | None = None) -> list[Character]:
    return list((await db.scalars(
        select(Character).where(
            Character.house_work.like(PREFIX + "%"), Character.house_work_until <= (now or _now()),
        ).with_for_update().execution_options(populate_existing=True)
    )).all())


# --- Еда в инвентаре ------------------------------------------------------------


async def add_food(db: AsyncSession, character_id: int, dish_id: str, grade: str, amount: int) -> None:
    row = await db.scalar(select(CharacterFood).where(
        CharacterFood.character_id == character_id, CharacterFood.dish_id == dish_id, CharacterFood.grade == grade,
    ))
    if row is None:
        row = CharacterFood(character_id=character_id, dish_id=dish_id, grade=grade, count=0)
        db.add(row)
    row.count += amount
    await db.flush()


async def get_food(db: AsyncSession, character_id: int) -> list[tuple[DishDef, cc.Dish, str, int]]:
    rows = (await db.scalars(select(CharacterFood).where(
        CharacterFood.character_id == character_id, CharacterFood.count > 0,
    ))).all()
    by_key = {(r.dish_id, r.grade): r.count for r in rows}
    out = []
    for dish in cc.DISHES:
        for grade in cc.GRADE_ORDER:
            n = by_key.get((dish.dish_id, grade))
            d = cooking.dish_def(dish.dish_id)
            if n and d is not None:
                out.append((d, dish, grade, n))
    return out


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


async def find_food(db: AsyncSession, character_id: int, query: str) -> list[tuple[DishDef, cc.Dish, str, int]]:
    """Блюда из сумки по названию (команда /съесть): точное совпадение, иначе
    начало или кусок названия. Лучшая градация рыбы - первой."""
    q = _norm(query)
    food = await get_food(db, character_id)
    exact = [f for f in food if _norm(f[0].name) == q]
    return exact or [f for f in food if q and q in _norm(f[0].name)]


async def eat(db: AsyncSession, character: Character, dish_id: str, grade: str, now: datetime | None = None) -> cc.Dish:
    """Съесть порцию: новое блюдо заменяет действующее."""
    row = await db.scalar(select(CharacterFood).where(
        CharacterFood.character_id == character.id, CharacterFood.dish_id == dish_id, CharacterFood.grade == grade,
    ).with_for_update().execution_options(populate_existing=True))
    dish = cc.DISHES_BY_ID.get(dish_id)
    if row is None or row.count < 1 or dish is None:
        raise CookingError("Этого блюда у тебя нет.")
    row.count -= 1
    # Пряности: заряд уходит на каждую съеденную порцию, пока они есть.
    from game.economy import craft_gear
    from services import craft_gear_service

    character.food_boost = craft_gear.spice_boost(await craft_gear_service.use_charge(db, character.id, "spices"))
    character.food_dish = dish_id
    character.food_grade = grade
    character.food_until = (now or _now()) + timedelta(minutes=cooking.food_minutes(character.cooking_level))
    await db.flush()
    return dish
