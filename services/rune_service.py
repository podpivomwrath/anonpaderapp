"""Руны (2026-10-31): сумка, мастерство, слоты, эффекты.

Решения владельца (память runes-plan): руна - обычный предмет, мастерство -
личное, копия впитывается без следа; вставлять и снимать руны бесплатно, но
только в родном городе; слоты героя - за золото; второе гнездо огранки открывает ступень II навыка.

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
    """Вставленные руны-навыки - это и есть навыки героя (2026-11-10)."""
    from game.combat import skill_catalog

    return skill_catalog.skills_of(character.rune_effects)


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

def _equipped(character: Character) -> tuple[list[str], dict[str, int]]:
    """Вставленные руны-навыки по порядку слотов и их ступени - из копии
    эффектов на персонаже (её обновляет recompute)."""
    from game.combat import skill_catalog

    effects = character.rune_effects or {}
    ids = skill_catalog.skill_ids_of(effects)
    return ids, {sid: int(effects.get(f"step:{sid}", 0)) for sid in ids}


def _slot_open(character: Character, kind: str, slot: str,
               state: tuple[list[str], dict[str, int]] | None = None) -> bool:
    if kind == rc.HERO:
        return slot.isdigit() and int(slot) < character.rune_hero_slots
    if kind == rc.ABILITY:
        return slot.isdigit() and int(slot) < rc.ABILITY_SLOTS
    place, _, index = slot.partition(":")
    if not index.isdigit():
        return False
    if kind == rc.GEAR:
        return place in rc.GEAR_PLACES and int(index) < rc.GEAR_SLOTS_PER_PLACE
    if kind == rc.SKILL:
        # Гнёзда огранок - внутри вставленной руны-навыка; второе открывает
        # ступень II этого навыка (2026-11-10, вместо покупки за золото).
        ids, steps = state or _equipped(character)
        if place not in ids:
            return False
        return int(index) == 0 or (int(index) == 1 and steps.get(place, 0) >= 2)
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
        from game.combat import skill_catalog

        skill = skill_catalog.skill_def(place)
        if skill is None or not runes.fits_skill(rune_def, skill):
            return f"Эта огранка - только в {rc.SKILL_TAG_TITLES[rune_def.tag]}."
    if kind == rc.ABILITY and not rune_def.ready:
        return "Этот навык пока не готов."
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
        # Одна руна вида - на героя одна, в экипировке одна, навык - в одном
        # слоте, огранка - одна на навык.
        if kind != rc.SKILL or row.slot.partition(":")[0] == place:
            raise RuneError("Такой навык уже вставлен." if kind == rc.ABILITY else "Такая руна уже вставлена.")
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


async def choose_fork(db: AsyncSession, character: Character, skill_id: str, fork: int) -> None:
    """Развилка ступени III: 1 - а, 2 - б. Бесплатно, только дома."""
    from game.economy import ability_config as ac

    if fork not in (1, 2) or skill_id not in ac.BY_ID:
        raise RuneError("Нет такой развилки.")
    if not at_home(character):
        raise RuneError("Развилку меняют только в родном городе.")
    known = await mastery(db, character.id)
    if ac.step_of(skill_id, known.get(skill_id, 0)) < 3:
        raise RuneError("Развилка открывается на третьей ступени.")
    character.skill_forks = {**(character.skill_forks or {}), skill_id: fork}  # JSON - целиком
    await db.flush()
    await recompute(db, character)


async def layout(db: AsyncSession, character: Character) -> list[dict]:
    """Вставленные руны - для пресета (репорт 340)."""
    rows = sorted(await slots(db, character.id), key=lambda r: (r.kind, r.slot))
    return [{"kind": r.kind, "slot": r.slot, "rune_id": r.rune_id} for r in rows]


async def apply_layout(db: AsyncSession, character: Character, saved: list) -> int:
    """Расставить руны по сохранённой раскладке: лишние - в сумку, нужные -
    из сумки. Возвращает, сколько рун не нашлось (продана, впитана, слот
    закрыт, не подходит). Руны-навыки ставятся первыми: от них зависят гнёзда
    огранок."""
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
    order = sorted(want.items(), key=lambda item: item[0][0] != rc.ABILITY)
    for (kind, slot), rune_id in order:
        if (kind, slot) in kept:
            continue
        if kind == rc.SKILL:
            await recompute(db, character)  # навыки уже стоят - гнёзда огранок открыты
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


async def grant_starter(db: AsyncSession, character: Character) -> list[str]:
    """Три стартовые руны-навыка класса от Хранителя Списков (2026-11-10):
    выдаются и сразу встают в пустые слоты навыков - без условия «дома»,
    это выбор класса, а не перестановка. Обычные руны: их можно продать и
    передать (твины запрещены, абуза нет - владелец). Возвращает id навыков."""
    from game.combat import skill_catalog

    starter = skill_catalog.STARTER_SKILLS.get(character.base_class or "", ())
    if any(r.kind == rc.ABILITY for r in await slots(db, character.id)):
        return []  # уже выдавали (возврат к выбору класса при создании)
    free = [str(i) for i in range(rc.ABILITY_SLOTS)]
    given = []
    for sid in starter:
        await grant(db, character.id, sid, 1, reason="starter")
        if free:
            await take(db, character.id, sid, 1)
            db.add(CharacterRuneSlot(character_id=character.id, kind=rc.ABILITY, slot=free.pop(0), rune_id=sid))
        given.append(sid)
    await db.flush()
    await recompute(db, character)
    return given


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


def _lost(character: Character, row: CharacterRuneSlot, state: tuple[list[str], dict[str, int]]) -> bool:
    """Руна, которой здесь больше не место: огранка навыка, который сняли
    (или второе гнездо без ступени II, или огранка не подходит после правки
    меток), руна экипировки чужого класса."""
    rune_def = rc.BY_ID.get(row.rune_id)
    if row.kind == rc.SKILL:
        if not _slot_open(character, rc.SKILL, row.slot, state):
            return True
        from game.combat import skill_catalog

        skill = skill_catalog.skill_def(row.slot.partition(":")[0])
        return rune_def is not None and (skill is None or not runes.fits_skill(rune_def, skill))
    return (row.kind == rc.GEAR and rune_def is not None
            and bool(rune_def.classes) and character.base_class not in rune_def.classes)


async def release_lost_runes(db: AsyncSession, character: Character) -> bool:
    """Огранки снятых навыков и руны экипировки чужого класса (репорт 266) -
    обратно в сумку."""
    known = await mastery(db, character.id)
    state = _state_from_rows(await slots(db, character.id), known)
    lost = [r for r in await slots(db, character.id) if _lost(character, r, state)]
    for row in lost:
        await grant(db, character.id, row.rune_id)
        await db.delete(row)
    if lost:
        await db.flush()
    return bool(lost)


def _state_from_rows(rows, known: dict[str, int]) -> tuple[list[str], dict[str, int]]:
    """Вставленные навыки и их ступени - по строкам слотов, не по копии."""
    from game.combat import skill_catalog
    from game.economy import ability_config as ac

    ability_rows = sorted(
        (r for r in rows if r.kind == rc.ABILITY and r.slot.isdigit() and int(r.slot) < rc.ABILITY_SLOTS
         and r.rune_id in skill_catalog.ALL_SKILL_DEFS),
        key=lambda r: int(r.slot),
    )
    ids = [r.rune_id for r in ability_rows]
    return ids, {sid: ac.step_of(sid, known.get(sid, 0)) for sid in ids}


async def recompute(db: AsyncSession, character: Character) -> dict[str, float]:
    """Пересчитать копию эффектов на персонаже. Огранки снятых навыков
    возвращаются в сумку. Руна-навык кладёт в копию: "ability:<id>" (слот +
    1), "rune:<id>" (сила от мастерства), "step:<id>" (ступень), "fork:<id>"
    (развилка, со ступени III)."""
    await release_lost_runes(db, character)
    known = await mastery(db, character.id)
    rows = await slots(db, character.id)
    state = _state_from_rows(rows, known)
    ids, steps = state
    forks = character.skill_forks or {}
    effects: dict[str, float] = {}
    for row in rows:
        rune_def = rc.BY_ID.get(row.rune_id)
        if rune_def is None or not _slot_open(character, row.kind, row.slot, state):
            continue
        if row.kind == rc.ABILITY:
            sid = row.rune_id
            if sid not in ids:
                continue
            effects[f"ability:{sid}"] = int(row.slot) + 1
            power = round(runes.value(rune_def, known.get(sid, 0)) - 1.0, 6)
            if power > 0:
                effects[runes.effect_key(sid)] = power
            if steps.get(sid):
                effects[f"step:{sid}"] = steps[sid]
            fork = forks.get(sid)
            if steps.get(sid, 0) >= 3 and fork in (1, 2):
                effects[f"fork:{sid}"] = fork
            continue
        skill_id = row.slot.partition(":")[0] if row.kind == rc.SKILL else None
        if row.kind == rc.GEAR and rune_def.classes and character.base_class not in rune_def.classes:
            continue
        key = runes.effect_key(row.rune_id, skill_id)
        effects[key] = round(runes.value(rune_def, known.get(row.rune_id, 0)), 6)
    character.rune_effects = effects
    await db.flush()
    return effects


# --- Выпадение -------------------------------------------------------------------

def roll_rune(rng: random.Random) -> str:
    """Какая руна выпала: из всех рун разом, вес - только редкость (2026-11-11,
    владелец: доли видов убраны, «полный рандом»). Только руны, чей эффект
    уже работает."""
    pool = [r for r in rc.RUNES if r.ready]
    return rng.choices(pool, weights=[rc.RARITY_WEIGHTS[r.rarity] for r in pool])[0].id


#: Перевес рун своего класса в ларце рун (2026-11-05, решение владельца:
#: под класс открывшего, но не только - дубли нужны рынку).
OWN_CLASS_WEIGHT = 3


def roll_rune_of_rarity(rng: random.Random, rarity: str, base_class: str | None = None) -> str:
    """Руна заданной редкости: любая, руны экипировки своего класса чаще."""
    pool = [r for r in rc.RUNES if r.ready and r.rarity == rarity] or [r for r in rc.RUNES if r.ready]
    weights = [OWN_CLASS_WEIGHT if base_class and base_class in r.classes else 1 for r in pool]
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


KIND_EMOJI = {rc.HERO: "🟠", rc.GEAR: "🔴", rc.SKILL: "🔵", rc.ABILITY: "🟣"}


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
