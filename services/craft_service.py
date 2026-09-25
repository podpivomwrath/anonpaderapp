"""Крафт специализированного оружия (патч 72): работа с БД.

Чистая логика (розыгрыш, эффективность, цены) — game/economy/crafting.py.
Здесь только состояние: списание руды, превращение предмета, инструменты.

Правила, задающие всю конструкцию:

1. Предмет-источник ПОТРЕБЛЯЕТСЯ. Цена попытки — сам источник, иначе
   перековывать можно было бы бесконечно за одну руду.

2. Скованное привязывается: ни передать, ни продать. Это лучшее оружие в
   игре, и добываться оно должно рейдом, а не покупкой у того, кому повезло.

3. Перекрафт мутирует ТОТ ЖЕ экземпляр, а не создаёт новый. Так счётчик
   перековок и надетость переживают операцию сами собой.
"""

import random
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy import craft_config as cc
from game.economy import crafting, mining
from models import Character, CharacterCraftTool, CharacterOre, Inventory, Item
from services import crown_service, item_service


class CraftError(Exception):
    """Игроко-читаемая причина отказа — тот же паттерн, что RaidError."""


# --- Руда ----------------------------------------------------------------------


async def ore_amount(db: AsyncSession, character_id: int, ore_id: str, grade: str) -> int:
    row = await db.scalar(
        select(CharacterOre.count).where(
            CharacterOre.character_id == character_id,
            CharacterOre.ore_id == ore_id,
            CharacterOre.grade == grade,
        )
    )
    return int(row or 0)


def _discounted(character: Character, cost: int) -> int:
    """Цена в руде с учётом венца «Клинок».

    Округление до ближайшего, но не ниже единицы: бесплатных операций в
    мастерской быть не должно даже при большой скидке.

    ЕДИНСТВЕННАЯ точка расчёта - её зовут и списание, и показ цены в
    мини-аппе. Раньше цена считалась в четырёх местах, и скидка неизбежно
    приехала бы не во все: игрок увидел бы одно число, а списалось бы
    другое, причём молча.
    """
    return max(1, round(cost * crown_service.craft_ore_multiplier(character)))


def first_craft_cost(character: Character) -> int:
    """Цена ковки предмета, которого ещё не ковали."""
    return _discounted(character, cc.CRAFT_ORE_COST)


def recraft_cost(character: Character, item: Item) -> int:
    """Цена следующей ковки этого предмета: первая - обычная, дальше дороже."""
    if item.craft_spec is None:
        return _discounted(character, cc.CRAFT_ORE_COST)
    return _discounted(character, cc.recraft_ore_cost(item.craft_recrafts))


def tool_cost(character: Character, ceiling: int) -> int:
    return _discounted(character, cc.tool_ore_cost(ceiling))


async def _spend_ore(
    db: AsyncSession, character_id: int, ore_id: str, grade: str, amount: int
) -> None:
    """Атомарное списание: порог проверяется в том же UPDATE.

    Чтение в питон и запись обратно открыли бы ту же гонку, что была на
    кошельке: вебхук обрабатывает события параллельно, и два нажатия
    «Сковать» успели бы потратить одну и ту же руду дважды.
    """
    result = await db.execute(
        update(CharacterOre)
        .where(
            CharacterOre.character_id == character_id,
            CharacterOre.ore_id == ore_id,
            CharacterOre.grade == grade,
            CharacterOre.count >= amount,
        )
        .values(count=CharacterOre.count - amount)
    )
    if not result.rowcount:
        have = await ore_amount(db, character_id, ore_id, grade)
        definition = mining.ore_def(ore_id)
        name = definition.name if definition else ore_id
        raise CraftError(
            f"Нужно {amount} ({name}, {mining.grade_name(grade)}), есть {have}."
        )


def _ore_tier(ore_id: str) -> int:
    definition = mining.ore_def(ore_id)
    if definition is None:
        raise CraftError("Такой руды не существует.")
    return definition.tier


# --- Предметы ------------------------------------------------------------------


async def _owned_item(db: AsyncSession, character_id: int, item_id: int) -> Item:
    row = await db.scalar(
        select(Inventory).where(
            Inventory.character_id == character_id, Inventory.item_id == item_id
        )
    )
    if row is None:
        raise CraftError("Этого предмета у тебя нет.")
    item = await db.get(Item, item_id)
    if item is None:
        raise CraftError("Этого предмета у тебя нет.")
    return item


def _primary_stat(character: Character) -> str:
    return bc.PRIMARY_STAT_BY_CLASS[character.base_class]


def source_of(item: Item) -> str | None:
    """Из чего этот предмет куётся (или уже скован).

    У боссовой вещи источник — она сама, у скованного оружия он записан при
    ковке. Благодаря этому перекрафт ищет рецепт по ИСТОЧНИКУ и не требует
    обратных рецептов на каждую пару специализаций.
    """
    return item.craft_source_id


# --- Ковка ---------------------------------------------------------------------


@dataclass
class CraftResult:
    item: Item
    spec: str
    efficiency: int
    stats: dict[str, int]
    ore_spent: int
    was_recraft: bool


async def craft(
    db: AsyncSession, character: Character, item_id: int, spec: str,
    ore_id: str, grade: str, rng: random.Random,
) -> CraftResult:
    """Кует оружие из боссовой вещи либо перековывает уже скованное.

    Одна функция на оба случая намеренно: разница только в цене и в том, что
    у перекрафта уже есть счётчик перековок. Разводить их значило бы дважды
    писать один и тот же розыгрыш.
    """
    if spec not in cc.SPECS:
        raise CraftError("Такой специализации нет.")

    item = await _owned_item(db, character.id, item_id)
    source_id = source_of(item)
    recipe = crafting.recipe_for(source_id) if source_id else None
    if recipe is None:
        raise CraftError("Из этого ничего не выковать.")

    tier = _ore_tier(ore_id)
    if tier > cc.CRAFT_MAX_ORE_TIER:
        raise CraftError(
            "Эта руда слишком хороша для ковки - выше "
            f"{cc.EFFICIENCY_CRAFT_MAX}% она всё равно не поднимет. "
            "Ей место в инструментах."
        )

    was_recraft = item.craft_spec is not None
    # Цену берём ДО правки предмета: ниже проставляется craft_spec и растёт
    # craft_recrafts, а от них она и зависит.
    cost = recraft_cost(character, item)
    await _spend_ore(db, character.id, ore_id, grade, cost)

    base_stats, efficiency = crafting.roll_crafted_stats(
        rng, spec, _source_power(item, recipe), _primary_stat(character), tier, grade
    )
    stats = crafting.stats_at_efficiency(base_stats, efficiency)

    item.name = recipe.outputs[spec].name
    item.base_stats = stats
    item.craft_base_stats = base_stats
    item.craft_spec = spec
    item.craft_efficiency = efficiency
    item.craft_source_id = source_id
    item.bound = True
    if was_recraft:
        item.craft_recrafts += 1
    await db.flush()

    return CraftResult(
        item=item, spec=spec, efficiency=efficiency, stats=stats,
        ore_spent=cost, was_recraft=was_recraft,
    )


def _source_power(item: Item, recipe) -> int:
    """Бюджет очков берётся от ИСХОДНОГО предмета, а не от текущих статов.

    Иначе перекрафт множил бы сам себя: оружие на 120% отдало бы в следующий
    ролл свою раздутую сумму, и каждая перековка делала бы предмет сильнее
    независимо от удачи.
    """
    unique = item_service.unique_items().get(item.craft_source_id)
    if unique is None:
        raise CraftError("Источник этого предмета не найден в каталоге.")
    return unique.power


# --- Инструменты ---------------------------------------------------------------


async def tools_of(db: AsyncSession, character_id: int) -> dict[int, int]:
    """{потолок: сколько штук} — только непустые."""
    rows = (
        await db.execute(
            select(CharacterCraftTool).where(
                CharacterCraftTool.character_id == character_id,
                CharacterCraftTool.count > 0,
            )
        )
    ).scalars().all()
    return {row.ceiling: row.count for row in rows}


async def make_tool(
    db: AsyncSession, character: Character, ore_id: str, grade: str
) -> int:
    """Кует инструмент. Возвращает его потолок."""
    tier = _ore_tier(ore_id)
    if tier > cc.TOOL_MAX_ORE_TIER:
        raise CraftError("Эта порода не идёт в инструменты.")
    ceiling = crafting.tool_ceiling_for(tier)
    if ceiling is None:
        raise CraftError("Из этой руды инструмент не выходит.")

    await _spend_ore(db, character.id, ore_id, grade, tool_cost(character, ceiling))

    row = await db.scalar(
        select(CharacterCraftTool).where(
            CharacterCraftTool.character_id == character.id,
            CharacterCraftTool.ceiling == ceiling,
        )
    )
    if row is None:
        row = CharacterCraftTool(character_id=character.id, ceiling=ceiling, count=0)
        db.add(row)
    row.count += 1
    await db.flush()
    return ceiling


async def _spend_tool(db: AsyncSession, character_id: int, ceiling: int) -> None:
    result = await db.execute(
        update(CharacterCraftTool)
        .where(
            CharacterCraftTool.character_id == character_id,
            CharacterCraftTool.ceiling == ceiling,
            CharacterCraftTool.count > 0,
        )
        .values(count=CharacterCraftTool.count - 1)
    )
    if not result.rowcount:
        raise CraftError("Такого инструмента у тебя нет.")


@dataclass
class UpgradeResult:
    item: Item
    efficiency_before: int
    efficiency_after: int
    stats: dict[str, int]


async def upgrade(
    db: AsyncSession, character: Character, item_id: int, ceiling: int
) -> UpgradeResult:
    """Поднимает эффективность на одну ступень, тратя инструмент.

    Неудачи здесь нет намеренно: риск оставлен будущему пробуждению, а
    лестница процентов — предсказуемая трата ресурсов.
    """
    item = await _owned_item(db, character.id, item_id)
    if item.craft_efficiency is None or item.craft_base_stats is None:
        raise CraftError("Этот предмет не выкован - улучшать нечего.")

    before = item.craft_efficiency
    nxt = crafting.next_efficiency(before)
    if nxt is None:
        raise CraftError(f"Уже {cc.EFFICIENCY_MAX}% - выше не бывает.")
    if not crafting.can_upgrade_with(before, ceiling):
        raise CraftError(
            f"Этот инструмент качает только до {ceiling}%, а нужна ступень {nxt}%."
        )

    await _spend_tool(db, character.id, ceiling)

    item.craft_efficiency = nxt
    item.base_stats = crafting.stats_at_efficiency(item.craft_base_stats, nxt)
    await db.flush()

    return UpgradeResult(
        item=item, efficiency_before=before, efficiency_after=nxt, stats=item.base_stats,
    )
