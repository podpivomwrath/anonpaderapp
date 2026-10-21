"""Травничество (2026-10-21): рост травы на клетках, сбор, сумка, опыт.

Логика без БД - game/economy/herbalism.py, числа - herbal_config.py.
Сервис не шлёт сообщений: тексты и кнопки - bot/handlers/herbs.py.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import HerbDef
from game.economy import herbal_config as hc
from game.economy import herbalism
from models import Character, CharacterHerb, HerbPatch


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fresh_since(now: datetime) -> datetime:
    return now - timedelta(hours=hc.LIFETIME_HOURS)


async def spawn(
    db: AsyncSession, rng: random.Random, explorer_cell: tuple[int, int], now: datetime | None = None,
) -> HerbPatch | None:
    """Исследование с шансом сажает траву на случайную клетку карты - не на
    ту, где исследовали. Заодно сметает завявшую."""
    now = now or _now()
    if rng.random() >= hc.SPAWN_CHANCE:
        return None
    await db.execute(delete(HerbPatch).where(HerbPatch.spawned_at < _fresh_since(now)))
    rows = (await db.execute(select(HerbPatch.x, HerbPatch.y))).all()
    if len(rows) >= hc.MAP_CAP:
        return None
    cell = herbalism.roll_cell(rng, {(x, y) for x, y in rows} | {explorer_cell})
    if cell is None:
        return None
    herb = herbalism.roll_herb(rng, *cell)
    patch = HerbPatch(x=cell[0], y=cell[1], herb_id=herb.id, spawned_at=now)
    db.add(patch)
    await db.flush()
    return patch


async def visible_here(db: AsyncSession, character: Character, now: datetime | None = None) -> tuple[HerbPatch, HerbDef] | None:
    """Трава на клетке персонажа, если он её различает."""
    now = now or _now()
    patch = await db.scalar(select(HerbPatch).where(
        HerbPatch.x == character.pos_x, HerbPatch.y == character.pos_y,
        HerbPatch.spawned_at >= _fresh_since(now),
    ))
    if patch is None:
        return None
    herb = herbalism.herb_def(patch.herb_id)
    if herb is None or not herbalism.can_see(character.herbalism_level, herb):
        return None
    return patch, herb


@dataclass
class PickResult:
    #: ok | gone | elsewhere | unseen
    status: str
    herb: HerbDef | None = None
    amount: int = 0
    xp: int = 0
    level_before: int = 0
    level_after: int = 0
    unlocked: list[HerbDef] = field(default_factory=list)


async def pick(
    db: AsyncSession, character: Character, patch_id: int, rng: random.Random, now: datetime | None = None,
) -> PickResult:
    """Сорвать траву. Строка под FOR UPDATE: двое нажали разом - трава у
    первого, второй дождётся и увидит, что её нет."""
    now = now or _now()
    patch = await db.scalar(
        select(HerbPatch).where(HerbPatch.id == patch_id).with_for_update().execution_options(populate_existing=True)
    )
    if patch is None or _aware(patch.spawned_at) < _fresh_since(now):
        return PickResult("gone")
    if (patch.x, patch.y) != (character.pos_x, character.pos_y):
        return PickResult("elsewhere")
    herb = herbalism.herb_def(patch.herb_id)
    if herb is None or not herbalism.can_see(character.herbalism_level, herb):
        return PickResult("unseen")
    await db.delete(patch)
    amount = 2 if rng.random() < herbalism.double_chance(character.herbalism_level) else 1
    await add_herb(db, character.id, herb.id, amount)
    xp = herbalism.pick_xp(herb)
    before = character.herbalism_level
    grant_xp(character, xp)
    await db.flush()
    return PickResult(
        "ok", herb=herb, amount=amount, xp=xp, level_before=before, level_after=character.herbalism_level,
        unlocked=herbalism.unlocked_between(before, character.herbalism_level),
    )


def grant_xp(character: Character, xp: int) -> None:
    if character.herbalism_level >= hc.MAX_LEVEL:
        return
    character.herbalism_xp += xp
    while character.herbalism_level < hc.MAX_LEVEL:
        need = herbalism.xp_to_next(character.herbalism_level)
        if character.herbalism_xp < need:
            break
        character.herbalism_xp -= need
        character.herbalism_level += 1
    if character.herbalism_level >= hc.MAX_LEVEL:
        character.herbalism_xp = 0


# --- Сумка --------------------------------------------------------------------


async def add_herb(db: AsyncSession, character_id: int, herb_id: str, amount: int) -> None:
    row = await db.scalar(select(CharacterHerb).where(
        CharacterHerb.character_id == character_id, CharacterHerb.herb_id == herb_id,
    ))
    if row is None:
        row = CharacterHerb(character_id=character_id, herb_id=herb_id, count=0)
        db.add(row)
    row.count += amount
    await db.flush()


async def get_bag(db: AsyncSession, character_id: int) -> list[tuple[HerbDef, int]]:
    """(трава, пучков) в порядке каталога, только непустые."""
    rows = (await db.execute(select(CharacterHerb.herb_id, CharacterHerb.count).where(
        CharacterHerb.character_id == character_id, CharacterHerb.count > 0,
    ))).all()
    counts = dict(rows)
    return [(h, counts[h.id]) for h in herbalism.herb_defs_ordered() if counts.get(h.id)]


async def alive_count(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or _now()
    return await db.scalar(select(func.count()).select_from(HerbPatch).where(
        HerbPatch.spawned_at >= _fresh_since(now)
    )) or 0
