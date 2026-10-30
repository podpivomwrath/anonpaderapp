"""Руны (2026-10-31): сумка, мастерство, слоты, эффекты.

Решения владельца (память runes-plan): руна - обычный предмет, мастерство -
личное, копия впитывается без следа; вставлять и снимать руны бесплатно, но
только в родном городе; слоты героя и вторые слоты навыков - за золото.

Сумма эффектов вставленных рун лежит копией на персонаже (rune_effects), как
guild_perks: её читают места без сессии БД (опыт, лут, отдых...). Её надо
пересчитывать после любой смены слота или мастерства - recompute.
"""

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import runes
from game.economy import runes_config as rc
from game.world import grid
from models import Character, CharacterRune, CharacterRuneMastery, CharacterRuneSlot
from services import wallet_service


class RuneError(Exception):
    pass


# --- Чтение ----------------------------------------------------------------------

async def bag(db: AsyncSession, character_id: int) -> dict[str, int]:
    rows = (await db.execute(select(CharacterRune).where(CharacterRune.character_id == character_id))).scalars()
    return {r.rune_id: r.count for r in rows if r.count > 0}


async def mastery(db: AsyncSession, character_id: int) -> dict[str, int]:
    rows = (await db.execute(
        select(CharacterRuneMastery).where(CharacterRuneMastery.character_id == character_id)
    )).scalars()
    return {r.rune_id: r.absorbed for r in rows}


async def slots(db: AsyncSession, character_id: int) -> list[CharacterRuneSlot]:
    return list((await db.execute(
        select(CharacterRuneSlot).where(CharacterRuneSlot.character_id == character_id)
    )).scalars())


def skills_of(character: Character) -> list:
    from game.combat.base_skills import skills_for_character

    return list(skills_for_character(character.base_class, character.subclass))


def at_home(character: Character) -> bool:
    """Руны меняют только в родном городе (владелец, 2026-10-31)."""
    return character.region is not None and grid.city_region_at(character.pos_x, character.pos_y) == character.region


def effect(character: Character, rune_id: str, skill_id: str | None = None, pvp: bool = False) -> float:
    """Текущая сила вставленной руны (в долях), 0 - если не вставлена."""
    value = (character.rune_effects or {}).get(runes.effect_key(rune_id, skill_id), 0.0)
    if not value or not pvp:
        return value
    return value * rc.PVP_MULT[rc.BY_ID[rune_id].pvp]


def combat_modifiers(character: Character, pvp: bool = False) -> dict[str, float]:
    """Эффекты рун для боя - ключи «rune:...» в buff_modifiers."""
    return runes.pvp_scaled(character.rune_effects or {}, pvp)


# --- Сумка и мастерство ----------------------------------------------------------

async def _bag_row(db: AsyncSession, character_id: int, rune_id: str, create: bool = False) -> CharacterRune | None:
    row = await db.scalar(
        select(CharacterRune).where(CharacterRune.character_id == character_id, CharacterRune.rune_id == rune_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if row is None and create:
        row = CharacterRune(character_id=character_id, rune_id=rune_id, count=0)
        db.add(row)
        await db.flush()
    return row


async def grant(db: AsyncSession, character_id: int, rune_id: str, count: int = 1, reason: str | None = None) -> None:
    if rune_id not in rc.BY_ID or count <= 0:
        raise RuneError("Нет такой руны.")
    row = await _bag_row(db, character_id, rune_id, create=True)
    row.count += count  # журнал ресурсов пишется сам (resource_log.TRACKED)
    await db.flush()


async def take(db: AsyncSession, character_id: int, rune_id: str, count: int = 1, reason: str | None = None) -> None:
    row = await _bag_row(db, character_id, rune_id)
    if row is None or row.count < count:
        raise RuneError("Такой руны в сумке нет.")
    row.count -= count
    await db.flush()


async def absorb(db: AsyncSession, character: Character, rune_id: str, count: int) -> int:
    """Впитать копии из сумки в мастерство. Возвращает новое мастерство."""
    if count <= 0:
        raise RuneError("Сколько впитать?")
    await take(db, character.id, rune_id, count)
    row = await db.scalar(
        select(CharacterRuneMastery).where(
            CharacterRuneMastery.character_id == character.id, CharacterRuneMastery.rune_id == rune_id,
        ).with_for_update()
    )
    if row is None:
        row = CharacterRuneMastery(character_id=character.id, rune_id=rune_id, absorbed=0)
        db.add(row)
    row.absorbed += count
    await db.flush()
    await recompute(db, character)
    return row.absorbed


# --- Слоты -----------------------------------------------------------------------

def _slot_open(character: Character, kind: str, slot: str) -> bool:
    if kind == rc.HERO:
        return slot.isdigit() and int(slot) < character.rune_hero_slots
    place, _, index = slot.partition(":")
    if not index.isdigit():
        return False
    if kind == rc.GEAR:
        return place in rc.GEAR_PLACES and int(index) < rc.GEAR_SLOTS_PER_PLACE
    if kind == rc.SKILL:
        if place not in {s.id for s in skills_of(character)}:
            return False
        return int(index) == 0 or (int(index) == 1 and place in (character.rune_skill_slots or []))
    return False


def _fits(character: Character, rune_def: rc.RuneDef, kind: str, slot: str) -> str | None:
    """Почему руна не встаёт в слот; None - встаёт."""
    if rune_def.kind != kind:
        return f"Это {rc.KIND_ONE[rune_def.kind].lower()}."
    place = slot.partition(":")[0]
    if kind == rc.GEAR and not runes.fits_gear(rune_def, place, character.base_class):
        if rune_def.classes and character.base_class not in rune_def.classes:
            return "Эта руна не для твоего класса."
        return "Оружейная руна - только в оружие." if rune_def.place == "weapon" else "Эта руна - в доспех."
    if kind == rc.SKILL:
        skill = next(s for s in skills_of(character) if s.id == place)
        if not runes.fits_skill(rune_def, skill):
            return f"Эта руна - только в {rc.SKILL_TAG_TITLES[rune_def.tag]}."
    return None


async def equip(db: AsyncSession, character: Character, kind: str, slot: str, rune_id: str) -> None:
    rune_def = rc.BY_ID.get(rune_id)
    if rune_def is None or kind not in rc.KINDS:
        raise RuneError("Нет такой руны.")
    if not at_home(character):
        raise RuneError("Руны меняют только в родном городе.")
    if not _slot_open(character, kind, slot):
        raise RuneError("Слот закрыт.")
    reason = _fits(character, rune_def, kind, slot)
    if reason:
        raise RuneError(reason)
    taken = await slots(db, character.id)
    place = slot.partition(":")[0]
    for row in taken:
        if row.kind != kind or row.slot == slot or row.rune_id != rune_id:
            continue
        # Одна руна вида - на героя одна, в экипировке одна, в навыке одна.
        if kind != rc.SKILL or row.slot.partition(":")[0] == place:
            raise RuneError("Такая руна уже вставлена.")
    await take(db, character.id, rune_id)
    current = next((r for r in taken if r.kind == kind and r.slot == slot), None)
    if current is not None:
        await grant(db, character.id, current.rune_id)
        current.rune_id = rune_id
    else:
        db.add(CharacterRuneSlot(character_id=character.id, kind=kind, slot=slot, rune_id=rune_id))
    await db.flush()
    await recompute(db, character)


async def unequip(db: AsyncSession, character: Character, kind: str, slot: str) -> None:
    if not at_home(character):
        raise RuneError("Руны меняют только в родном городе.")
    row = next((r for r in await slots(db, character.id) if r.kind == kind and r.slot == slot), None)
    if row is None:
        raise RuneError("Слот пуст.")
    await grant(db, character.id, row.rune_id)
    await db.delete(row)
    await db.flush()
    await recompute(db, character)


async def buy_hero_slot(db: AsyncSession, character: Character) -> int:
    price = runes.hero_slot_price(character.rune_hero_slots)
    if price is None:
        raise RuneError("Все слоты уже открыты.")
    try:
        await wallet_service.charge(db, character.id, "farm", price)
    except wallet_service.NotEnoughCurrency:
        raise RuneError(f"Нужно {price:,} золота.".replace(",", " ")) from None
    character.rune_hero_slots += 1
    await db.flush()
    return character.rune_hero_slots


async def buy_skill_slot(db: AsyncSession, character: Character, skill_id: str) -> None:
    if skill_id not in {s.id for s in skills_of(character)}:
        raise RuneError("Нет такого навыка.")
    owned = list(character.rune_skill_slots or [])
    if skill_id in owned:
        raise RuneError("Второй слот уже открыт.")
    try:
        await wallet_service.charge(db, character.id, "farm", rc.SKILL_SLOT_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise RuneError(f"Нужно {rc.SKILL_SLOT_PRICE:,} золота.".replace(",", " ")) from None
    character.rune_skill_slots = owned + [skill_id]  # JSON заменяется целиком
    await db.flush()


async def recompute(db: AsyncSession, character: Character) -> dict[str, float]:
    """Пересчитать копию эффектов на персонаже. Руна навыка, которого больше
    нет (сменил путь), не действует, но остаётся в слоте."""
    known = await mastery(db, character.id)
    skill_ids = {s.id for s in skills_of(character)}
    effects: dict[str, float] = {}
    for row in await slots(db, character.id):
        rune_def = rc.BY_ID.get(row.rune_id)
        if rune_def is None or not _slot_open(character, row.kind, row.slot):
            continue
        skill_id = None
        if row.kind == rc.SKILL:
            skill_id = row.slot.partition(":")[0]
            if skill_id not in skill_ids:
                continue
        if row.kind == rc.GEAR and rune_def.classes and character.base_class not in rune_def.classes:
            continue
        key = runes.effect_key(row.rune_id, skill_id)
        effects[key] = round(runes.value(rune_def, known.get(row.rune_id, 0)), 6)
    character.rune_effects = effects
    await db.flush()
    return effects


# --- Выпадение -------------------------------------------------------------------

def roll_rune(rng: random.Random) -> str:
    """Какая руна выпала: вид по весам, затем руна по редкости. Только руны,
    чей эффект уже работает."""
    kinds = list(rc.KIND_WEIGHTS)
    kind = rng.choices(kinds, weights=[rc.KIND_WEIGHTS[k] for k in kinds])[0]
    pool = [r for r in rc.RUNES if r.kind == kind and r.ready]
    if not pool:
        pool = [r for r in rc.RUNES if r.ready]
    return rng.choices(pool, weights=[rc.RARITY_WEIGHTS[r.rarity] for r in pool])[0].id


async def maybe_drop(db: AsyncSession, character: Character, rng: random.Random,
                     chance: float = rc.MOB_DROP_CHANCE) -> str | None:
    """Бросок на руну за победу. Возвращает id выпавшей руны."""
    if rng.random() >= chance:
        return None
    rune_id = roll_rune(rng)
    await grant(db, character.id, rune_id)
    return rune_id


KIND_EMOJI = {rc.HERO: "🟠", rc.GEAR: "🔴", rc.SKILL: "🔵"}


async def drop_line(db: AsyncSession, character: Character, rng: random.Random) -> str | None:
    """Строка в итог победы, если выпала руна."""
    rune_id = await maybe_drop(db, character, rng)
    if rune_id is None:
        return None
    rune_def = rc.BY_ID[rune_id]
    return f"{KIND_EMOJI[rune_def.kind]} Руна «{rune_def.name}»."
