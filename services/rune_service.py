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
            return "Эта руна не для вашего класса."
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


async def layout(db: AsyncSession, character: Character) -> list[dict]:
    """Вставленные руны - для пресета (репорт 340)."""
    rows = sorted(await slots(db, character.id), key=lambda r: (r.kind, r.slot))
    return [{"kind": r.kind, "slot": r.slot, "rune_id": r.rune_id} for r in rows]


async def apply_layout(db: AsyncSession, character: Character, saved: list) -> int:
    """Расставить руны по сохранённой раскладке: лишние - в сумку, нужные -
    из сумки. Возвращает, сколько рун не нашлось (продана, впитана, слот
    закрыт, не подходит после смены пути)."""
    if not at_home(character):
        raise RuneError("Руны меняют только в родном городе.")
    want: dict[tuple[str, str], str] = {}
    for e in saved or []:
        if isinstance(e, dict) and e.get("kind") in rc.KINDS and isinstance(e.get("slot"), str):
            want[(e["kind"], e["slot"])] = str(e.get("rune_id"))
    kept: set[tuple[str, str]] = set()
    for row in await slots(db, character.id):
        if want.get((row.kind, row.slot)) == row.rune_id:
            kept.add((row.kind, row.slot))
            continue
        await grant(db, character.id, row.rune_id)
        await db.delete(row)
    await db.flush()
    missing = 0
    for (kind, slot), rune_id in want.items():
        if (kind, slot) in kept:
            continue
        rune_def = rc.BY_ID.get(rune_id)
        if rune_def is None or not _slot_open(character, kind, slot) or _fits(character, rune_def, kind, slot):
            missing += 1
            continue
        row = await _bag_row(db, character.id, rune_id)
        if row is None or row.count < 1:
            missing += 1
            continue
        row.count -= 1
        db.add(CharacterRuneSlot(character_id=character.id, kind=kind, slot=slot, rune_id=rune_id))
    await db.flush()
    await recompute(db, character)
    return missing


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


def spare_skill_slots(character: Character) -> int:
    """Купленные вторые слоты у навыков, которых у героя больше нет (подкласс
    заменил навыки класса, сброс пути). Владелец, 2026-10-31: 1 покупка = 1
    доп. слот - такой слот переносится на любой текущий навык бесплатно."""
    skill_ids = {s.id for s in skills_of(character)}
    return sum(1 for sid in character.rune_skill_slots or [] if sid not in skill_ids)


def settle_skill_slots(character: Character) -> bool:
    """Купленные вторые слоты прежних навыков сами переходят на текущие
    навыки без слота, по порядку навыков (2026-11-04, игроки: после смены
    класса слоты приходилось переносить вручную в каждом навыке). Вернулся
    к прежнему пути - слоты так же переедут обратно. True - что-то перенесли.

    Обратно - на тот же навык, где слот был (репорт 333: у Тёмного мистика
    слот с «Круга тьмы» после смены пути и возврата встал на «Кровавый
    пакт», первый по порядку). Откуда пришёл каждый слот - ui_flags."""
    skill_ids = [s.id for s in skills_of(character)]
    owned = list(character.rune_skill_slots or [])
    missing = [sid for sid in skill_ids if sid not in owned]
    flags = dict(getattr(character, "ui_flags", None) or {})
    came_from = dict(flags.get(_SLOT_FROM) or {})
    moved = False
    for i, sid in enumerate(owned):
        if not missing:
            break
        if sid not in skill_ids:
            target = _slot_home(sid, came_from, missing)
            missing.remove(target)
            owned[i] = target
            came_from[target] = sid
            moved = True
    if moved:
        character.rune_skill_slots = owned  # JSON заменяется целиком
        if hasattr(character, "ui_flags"):
            flags[_SLOT_FROM] = came_from
            character.ui_flags = flags
    return moved


_SLOT_FROM = "rune_slot_from"


def _slot_home(sid: str, came_from: dict[str, str], missing: list[str]) -> str:
    """Куда вернуть слот с ушедшего навыка sid: навык, откуда он когда-то
    пришёл, если этот навык снова есть и без слота, иначе первый свободный."""
    seen = {sid}
    prev = came_from.get(sid)
    while prev and prev not in seen:
        if prev in missing:
            return prev
        seen.add(prev)
        prev = came_from.get(prev)
    return missing[0]


async def buy_skill_slot(db: AsyncSession, character: Character, skill_id: str) -> None:
    skill_ids = {s.id for s in skills_of(character)}
    if skill_id not in skill_ids:
        raise RuneError("Нет такого навыка.")
    owned = list(character.rune_skill_slots or [])
    if skill_id in owned:
        raise RuneError("Второй слот уже открыт.")
    spare = next((i for i, sid in enumerate(owned) if sid not in skill_ids), None)
    if spare is not None:
        owned[spare] = skill_id  # перенос купленного слота, без платы
        character.rune_skill_slots = owned  # JSON заменяется целиком
        await db.flush()
        return
    try:
        await wallet_service.charge(db, character.id, "farm", rc.SKILL_SLOT_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise RuneError(f"Нужно {rc.SKILL_SLOT_PRICE:,} золота.".replace(",", " ")) from None
    character.rune_skill_slots = owned + [skill_id]
    await db.flush()


def _lost(character: Character, row: CharacterRuneSlot, skill_ids: set[str]) -> bool:
    """Руна, которой после смены класса или пути здесь не место, или руна
    навыка, которую этот навык больше не принимает (правка тегов)."""
    rune_def = rc.BY_ID.get(row.rune_id)
    if row.kind == rc.SKILL:
        place = row.slot.partition(":")[0]
        if place not in skill_ids:
            return True
        skill = next(s for s in skills_of(character) if s.id == place)
        return rune_def is not None and not runes.fits_skill(rune_def, skill)
    return (row.kind == rc.GEAR and rune_def is not None
            and bool(rune_def.classes) and character.base_class not in rune_def.classes)


async def release_lost_runes(db: AsyncSession, character: Character) -> bool:
    """Руны из слотов навыков, которых у героя больше нет, и руны экипировки
    чужого класса (репорт 266) - обратно в сумку."""
    skill_ids = {s.id for s in skills_of(character)}
    lost = [r for r in await slots(db, character.id) if _lost(character, r, skill_ids)]
    for row in lost:
        await grant(db, character.id, row.rune_id)
        await db.delete(row)
    if lost:
        await db.flush()
    return bool(lost)


async def recompute(db: AsyncSession, character: Character) -> dict[str, float]:
    """Пересчитать копию эффектов на персонаже. Руны навыков, которых больше
    нет (сменил путь), возвращаются в сумку."""
    await release_lost_runes(db, character)
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


#: Перевес рун своего класса в ларце рун (2026-11-05, решение владельца:
#: под класс открывшего, но не только - дубли нужны рынку).
OWN_CLASS_WEIGHT = 3


def roll_rune_of_rarity(rng: random.Random, rarity: str, base_class: str | None = None) -> str:
    """Руна заданной редкости: вид по весам, руны своего класса чаще."""
    pool = [r for r in rc.RUNES if r.ready and r.rarity == rarity] or [r for r in rc.RUNES if r.ready]
    weights = [
        rc.KIND_WEIGHTS[r.kind] * (OWN_CLASS_WEIGHT if base_class and base_class in r.classes else 1)
        for r in pool
    ]
    return rng.choices(pool, weights=weights)[0].id


def rune_title(rune_id: str) -> str:
    rune_def = rc.BY_ID.get(rune_id)
    if rune_def is None:
        return rune_id
    return f"{KIND_EMOJI[rune_def.kind]} {rune_def.name}"


async def maybe_drop(db: AsyncSession, character: Character, rng: random.Random,
                     chance: float = rc.MOB_DROP_CHANCE) -> str | None:
    """Бросок на руну за победу. Возвращает id выпавшей руны."""
    if rng.random() >= chance:
        return None
    rune_id = roll_rune(rng)
    await grant(db, character.id, rune_id)
    return rune_id


KIND_EMOJI = {rc.HERO: "🟠", rc.GEAR: "🔴", rc.SKILL: "🔵"}


def ring_line(ring: str) -> str:
    """Строка о найденном Перстне Несгоревшего: worn - надет сам, bag - в сумке."""
    from game.economy import resists

    if ring == "worn":
        return (f"💍 Среди добычи - кольцо: «{resists.RING_TITLE}». Оно уже на пальце, "
                "смотрите во вкладке «Герой».")
    return (f"💍 Среди добычи - кольцо: «{resists.RING_TITLE}». Палец занят, оно в сумке: "
            "поменять кольца можно во вкладке «Герой», лишнее - передать или продать на рынке.")


async def drop_line(db: AsyncSession, character: Character, rng: random.Random) -> str | None:
    """Строка в итог победы, если выпала руна. Тот же бросок победы - и
    Перстень Несгоревшего (2026-11-02): строка только у нашедшего."""
    from game.economy import brand_config as brc
    from services import premium_service, resist_service

    lines = []
    chance = rc.MOB_DROP_CHANCE * (brc.RUNE_DROP_MULT if premium_service.is_brand(character) else 1.0)
    rune_id = await maybe_drop(db, character, rng, chance)
    if rune_id is not None:
        rune_def = rc.BY_ID[rune_id]
        lines.append(f"{KIND_EMOJI[rune_def.kind]} Выпала {rc.KIND_ONE[rune_def.kind].lower()}: «{rune_def.name}»")
    ring = await resist_service.maybe_drop_ring(db, character, rng)
    if ring is not None:
        lines.append(ring_line(ring))
    return "\n".join(lines) or None
