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
    herb = herbalism.roll_herb(rng, await herbalists_level(db, now))
    patch = HerbPatch(x=cell[0], y=cell[1], herb_id=herb.id, spawned_at=now)
    db.add(patch)
    await db.flush()
    return patch


async def herbalists_level(db: AsyncSession, now: datetime | None = None) -> float:
    """Средний уровень травников в сети (2026-10-22): от него - тир новой
    травы. Травник - кто уже рвал траву (уровень выше 1 или есть опыт).
    Никого в сети - средний за сутки, никого и за сутки - 1."""
    now = now or _now()
    for minutes in (hc.ONLINE_MINUTES, 24 * 60):
        levels = list(await db.scalars(select(Character.herbalism_level).where(
            Character.creation_state.is_(None),
            Character.last_active_at >= now - timedelta(minutes=minutes),
            (Character.herbalism_level > 1) | (Character.herbalism_xp > 0),
        )))
        if levels:
            return sum(levels) / len(levels)
    return 1.0


async def regrow_all(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> int:
    """Перерастить всю траву на карте под нынешних травников: клетки и
    время остаются, вид травы выбирается заново (2026-10-22, разово после
    смены правила)."""
    now = now or _now()
    level = await herbalists_level(db, now)
    patches = list(await db.scalars(select(HerbPatch).where(HerbPatch.spawned_at >= _fresh_since(now))))
    for patch in patches:
        patch.herb_id = herbalism.roll_herb(rng, level).id
    await db.flush()
    return len(patches)


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


async def visible_around(
    db: AsyncSession, character: Character, now: datetime | None = None,
) -> list[tuple[int, tuple[int, int], HerbDef]]:
    """Трава на восьми соседних клетках, которую персонаж различает:
    [(id куста, (dx, dy), трава)] - для альманаха травника (2026-10-23)."""
    now = now or _now()
    x, y = character.pos_x, character.pos_y
    rows = (await db.scalars(select(HerbPatch).where(
        HerbPatch.x.between(x - 1, x + 1), HerbPatch.y.between(y - 1, y + 1),
        HerbPatch.spawned_at >= _fresh_since(now),
    ))).all()
    out = []
    for patch in rows:
        if (patch.x, patch.y) == (x, y):
            continue
        herb = herbalism.herb_def(patch.herb_id)
        if herb is not None and herbalism.can_see(character.herbalism_level, herb):
            out.append((patch.id, (patch.x - x, patch.y - y), herb))
    return sorted(out, key=lambda item: item[1])


async def fresh_patch_ids(db: AsyncSession, ids: set[int], now: datetime | None = None) -> set[int]:
    """Какие из этих кустов ещё растут (не сорваны и не завяли)."""
    if not ids:
        return set()
    now = now or _now()
    return set(await db.scalars(select(HerbPatch.id).where(
        HerbPatch.id.in_(ids), HerbPatch.spawned_at >= _fresh_since(now),
    )))


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
    from services import rune_service

    chance = herbalism.double_chance(character.herbalism_level) + rune_service.effect(character, "green_fingers")
    lucky = rng.random() < chance
    amount = 2 if lucky else 1
    from services import master_recipe_service

    if master_recipe_service.has_ring(character):
        # Перстень: всегда вдвое, шанс двойного сбора становится шансом тройного.
        amount = 3 if lucky else 2
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


async def spend(db: AsyncSession, character_id: int, needs: dict[str, int]) -> bool:
    """Списать пучки разом; не хватает хоть одного - не списывается ничего."""
    rows = (await db.scalars(select(CharacterHerb).where(
        CharacterHerb.character_id == character_id, CharacterHerb.herb_id.in_(list(needs)),
    ).with_for_update().execution_options(populate_existing=True))).all()
    have = {r.herb_id: r for r in rows}
    if any(have.get(h) is None or have[h].count < n for h, n in needs.items()):
        return False
    for h, n in needs.items():
        have[h].count -= n
    await db.flush()
    return True


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
