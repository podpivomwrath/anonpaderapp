"""Ремесленные инструменты (2026-10-23): владение, изготовление, заряды.

Правила - game/economy/craft_gear.py, числа - craft_gear_config.py.
Инструмент - строка CharacterCraftGear: одна на инструмент персонажа, сразу
в слоте. Новая ковка тира выше заменяет старую; ниже или того же - отказ.
"""

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import craft_gear, fishing, herbalism, mining
from game.economy import craft_gear_config as gc
from models import Character, CharacterCraftGear, CharacterFish, CharacterHerb, CharacterOre

_GRADE_RANK = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}


class GearError(Exception):
    """Игроку понятная причина отказа."""


async def gear(db: AsyncSession, character_id: int) -> dict[str, CharacterCraftGear]:
    rows = (await db.scalars(select(CharacterCraftGear).where(
        CharacterCraftGear.character_id == character_id,
    ))).all()
    return {r.tool_id: r for r in rows}


async def tier(db: AsyncSession, character_id: int, tool_id: str) -> int:
    """Тир инструмента; 0 - его нет. У расходников - 0, если кончились."""
    row = await db.scalar(select(CharacterCraftGear).where(
        CharacterCraftGear.character_id == character_id, CharacterCraftGear.tool_id == tool_id,
    ))
    if row is None:
        return 0
    tool = craft_gear.tool_def(tool_id)
    if tool is not None and tool.source in ("charges", "stock") and row.count <= 0:
        return 0
    return row.tier


async def _row(db: AsyncSession, character_id: int, tool_id: str) -> CharacterCraftGear | None:
    return await db.scalar(select(CharacterCraftGear).where(
        CharacterCraftGear.character_id == character_id, CharacterCraftGear.tool_id == tool_id,
    ).with_for_update().execution_options(populate_existing=True))


async def almanac_use(db: AsyncSession, character_id: int, now=None) -> tuple[int, int] | None:
    """Альманах подсказывает траву сейчас? Тратит одно срабатывание; последнее
    запускает час зарядки, после неё запас снова полный. (осталось, всего)
    после этого срабатывания; None - альманаха нет или он заряжается."""
    from datetime import datetime, timezone

    row = await _row(db, character_id, "almanac")
    if row is None:
        return None
    now = now or datetime.now(timezone.utc)
    if row.cycle_at is not None:
        if craft_gear.almanac_charge_left(row.cycle_at, now):
            return None
        row.cycle_at, row.used = None, 0
    total = craft_gear.almanac_uses(row.count)
    row.used = (row.used or 0) + 1
    if row.used >= total:
        row.cycle_at = now
    await db.flush()
    return max(total - row.used, 0), total


def almanac_herb_set(row) -> set[str] | None:
    """Какие травы подсказывает альманах: None - всю, что персонаж различает;
    пустое множество - никакую. У строк до 0097 - травы выбранного тира."""
    if row is None:
        return None
    if row.herb_ids is not None:
        return {h for h in row.herb_ids.split(",") if h}
    if row.herb_tier is not None:
        return {h.id for h in herbalism.herb_defs_ordered() if h.tier == row.herb_tier}
    return None


async def almanac_filter(db: AsyncSession, character_id: int) -> set[str] | None:
    """Травы, которые подсказывает альманах (см. almanac_herb_set)."""
    row = await db.scalar(select(CharacterCraftGear).where(
        CharacterCraftGear.character_id == character_id, CharacterCraftGear.tool_id == "almanac",
    ))
    return almanac_herb_set(row)


async def set_almanac_herbs(db: AsyncSession, character: Character, herb_ids: list[str] | None) -> None:
    """Галочки по траве (2026-10-29, владелец): None - вся трава, пустой
    список - альманах молчит. Только трава, которую персонаж различает.
    Отмечена вся, что различает, - пишем «всю»: новая трава после роста
    травничества тогда тоже попадёт в подсказки."""
    row = await _row(db, character.id, "almanac")
    if row is None:
        raise GearError("Альманаха нет.")
    ordered = herbalism.herb_defs_ordered()
    visible = {h.id for h in ordered if herbalism.can_see(character.herbalism_level, h)}
    if herb_ids is not None:
        chosen = set(herb_ids)
        if not chosen <= visible:
            raise GearError("Эту траву ты пока не различаешь.")
        herb_ids = None if chosen == visible else [h.id for h in ordered if h.id in chosen]
    row.herb_ids = None if herb_ids is None else ",".join(herb_ids)
    row.herb_tier = None
    await db.flush()


async def use_charge(db: AsyncSession, character_id: int, tool_id: str) -> int:
    """Потратить заряд (пряности) или штуку (склянки). Тир или 0 - нечего тратить."""
    row = await _row(db, character_id, tool_id)
    if row is None or row.count <= 0:
        return 0
    row.count -= 1
    await db.flush()
    return row.tier


async def grant_drop(db: AsyncSession, character_id: int, tool_id: str) -> bool:
    """Выдать добываемый инструмент (альманах, лампа). False - уже есть."""
    if await _row(db, character_id, tool_id) is not None:
        return False
    db.add(CharacterCraftGear(character_id=character_id, tool_id=tool_id, tier=1, count=0))
    await db.flush()
    return True


ALMANAC_LINE = "📗 Среди вещей моба - потрёпанный альманах травника. Теперь видно траву на соседних клетках."
LAMP_LINE = (
    "🏮 В разломе нашлась шахтёрская лампа: жилы с исследования копаются быстрее, "
    "а в руде иногда попадается 💎."
)


async def roll_almanac(db: AsyncSession, character: Character, rng: random.Random) -> str | None:
    """Альманах с моба: шанс gc.ALMANAC_DROP_CHANCE, если его ещё нет. У кого
    уже есть - с тем же шансом страница: +2 срабатывания навсегда (2026-10-29)."""
    if rng.random() >= gc.ALMANAC_DROP_CHANCE:
        return None
    row = await _row(db, character.id, "almanac")
    if row is None:
        return ALMANAC_LINE if await grant_drop(db, character.id, "almanac") else None
    row.count = (row.count or 0) + 1
    await db.flush()
    return (f"📗 Страница альманаха: +{gc.ALMANAC_USES_PER_PAGE} подсказки до зарядки, "
            f"теперь {craft_gear.almanac_uses(row.count)}.")


async def roll_lamp(db: AsyncSession, character_id: int, rng: random.Random) -> str | None:
    """Лампа за пройденный разлом: шанс gc.LAMP_RIFT_CHANCE, если её ещё нет."""
    if rng.random() >= gc.LAMP_RIFT_CHANCE:
        return None
    return LAMP_LINE if await grant_drop(db, character_id, "lamp") else None


# --- Материалы -------------------------------------------------------------------


async def _ore_rows(db: AsyncSession, character_id: int, ore_tier: int) -> list[CharacterOre]:
    ids = [o.id for o in mining.ore_defs_ordered() if o.tier == ore_tier]
    rows = (await db.scalars(select(CharacterOre).where(
        CharacterOre.character_id == character_id, CharacterOre.ore_id.in_(ids), CharacterOre.count > 0,
    ).with_for_update().execution_options(populate_existing=True))).all()
    # Сначала уходит руда попроще: редкую градацию берегут для кузни оружия.
    return sorted(rows, key=lambda r: _GRADE_RANK.get(r.grade, 0))


async def _herb_rows(db: AsyncSession, character_id: int, herb_tier: int) -> list[CharacterHerb]:
    ids = [h.id for h in herbalism.herb_defs_ordered() if h.tier == herb_tier]
    rows = (await db.scalars(select(CharacterHerb).where(
        CharacterHerb.character_id == character_id, CharacterHerb.herb_id.in_(ids), CharacterHerb.count > 0,
    ).with_for_update().execution_options(populate_existing=True))).all()
    return sorted(rows, key=lambda r: -r.count)


def _take(rows, amount: int) -> None:
    for row in rows:
        if amount <= 0:
            break
        part = min(row.count, amount)
        row.count -= part
        amount -= part


async def ore_have(db: AsyncSession, character_id: int, ore_tier: int) -> int:
    return sum(r.count for r in await _ore_rows(db, character_id, ore_tier))


async def herbs_have(db: AsyncSession, character_id: int, herb_tier: int) -> int:
    return sum(r.count for r in await _herb_rows(db, character_id, herb_tier))


async def fish_have(db: AsyncSession, character_id: int) -> int:
    rows = (await db.scalars(select(CharacterFish).where(CharacterFish.character_id == character_id))).all()
    return sum(r.total_grams for r in rows)


def recipe(tool: gc.ToolDef, tier: int) -> dict[str, int]:
    """Что уходит на изготовление: {"ore": n, "herbs": n, "fish_g": n} тира tier."""
    if tool.source == "forge":
        out = {"ore": tool.cost}
        if tool.herbs:
            out["herbs"] = tool.herbs
        return out
    if tool.source in ("herbs", "charges"):
        return {"herbs": tool.cost}
    if tool.source == "stock":
        out = {k: v for k, v in (("ore", tool.cost), ("herbs", tool.herbs), ("fish_g", tool.fish_g)) if v}
        return out
    return {}


# --- Изготовление ------------------------------------------------------------------


async def make(db: AsyncSession, character: Character, tool_id: str, tier: int) -> CharacterCraftGear:
    """Сковать/сплести/собрать инструмент тира tier. Материалы того же тира
    (склянки - всегда руда 1 тира). Ниже или тот же тир, что уже есть, - отказ
    (кроме зарядов и склянок: их докупают сколько угодно)."""
    tool = craft_gear.tool_def(tool_id)
    if tool is None or tool.source == "drop":
        raise GearError("Это не делают руками - только находят.")
    if tool.source == "stock":
        tier = 1
    if tier not in gc.TIERS:
        raise GearError("Нет такого тира.")
    level_field = gc.CRAFTS[tool.craft][2]
    need_level = craft_gear.level_for(tool, tier)
    if getattr(character, level_field) < need_level:
        raise GearError(f"Нужен {need_level} уровень ремесла «{gc.CRAFTS[tool.craft][1]}».")
    row = await _row(db, character.id, tool_id)
    stackable = tool.source in ("charges", "stock")
    if row is not None and not stackable and row.tier >= tier:
        raise GearError("У тебя уже есть такой или лучше.")

    needs = recipe(tool, tier)
    ore_tier = 1 if tool.source == "stock" else tier
    ore_rows = await _ore_rows(db, character.id, ore_tier) if needs.get("ore") else []
    herb_rows = await _herb_rows(db, character.id, tier) if needs.get("herbs") else []
    if needs.get("ore") and sum(r.count for r in ore_rows) < needs["ore"]:
        raise GearError(f"Нужно {needs['ore']} руды {ore_tier} тира.")
    if needs.get("herbs") and sum(r.count for r in herb_rows) < needs["herbs"]:
        raise GearError(f"Нужно {needs['herbs']} пучков травы {tier} тира.")
    fish_rows = []
    if needs.get("fish_g"):
        fish_rows = (await db.scalars(select(CharacterFish).where(
            CharacterFish.character_id == character.id, CharacterFish.total_grams > 0,
        ).with_for_update().execution_options(populate_existing=True))).all()
        if sum(r.total_grams for r in fish_rows) < needs["fish_g"]:
            raise GearError(f"Нужно {fishing.format_kg(needs['fish_g'])} любой рыбы.")

    _take(ore_rows, needs.get("ore", 0))
    _take(herb_rows, needs.get("herbs", 0))
    left = needs.get("fish_g", 0)
    for fish in sorted(fish_rows, key=lambda r: _GRADE_RANK.get(r.grade, 0)):
        if left <= 0:
            break
        part = min(fish.total_grams, left)
        fish.total_grams -= part
        left -= part

    if row is None:
        row = CharacterCraftGear(character_id=character.id, tool_id=tool_id, tier=tier, count=0)
        db.add(row)
    if tool.source == "charges":
        # Другой тир пряностей - новый набор: старые заряды не смешиваются.
        if row.tier != tier:
            row.count = 0
        row.tier = tier
        row.count = (row.count or 0) + tool.yield_
    elif tool.source == "stock":
        row.count = (row.count or 0) + tool.yield_
    else:
        row.tier = tier
    await db.flush()
    return row


# --- Прикормка (2026-10-23) -----------------------------------------------------


def bait_minutes_left(character: Character, now=None) -> int:
    """Сколько минут ещё клюёт быстрее; 0 - прикормки нет."""
    from datetime import datetime, timezone

    until = character.bait_until
    if until is None:
        return 0
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    left = (until - (now or datetime.now(timezone.utc))).total_seconds()
    return max(0, -(-int(left) // 60))


def bite_mult(character: Character) -> float:
    """Во сколько раз короче ожидание поклёвки (прикормка)."""
    return 1.0 - gc.BAIT_SPEED if bait_minutes_left(character) > 0 else 1.0


async def use_bait(db: AsyncSession, character: Character) -> int:
    """Рассыпать прикормку: время складывается с оставшимся. Минут всего."""
    from datetime import datetime, timedelta, timezone

    if not await use_charge(db, character.id, "bait"):
        raise GearError("Прикормки нет.")
    now = datetime.now(timezone.utc)
    start = now
    if bait_minutes_left(character, now) > 0:
        start = character.bait_until if character.bait_until.tzinfo else character.bait_until.replace(tzinfo=timezone.utc)
    character.bait_until = start + timedelta(minutes=gc.BAIT_MINUTES)
    await db.flush()
    return bait_minutes_left(character, now)
