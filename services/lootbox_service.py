"""Пепельный ларец (патч 24): 1 ларец за каждый день стрика ежедневок.

С патча 106 ларец ложится в сумку закрытым (grant_chest), а открывает его
игрок сам - в мини-аппе, рулеткой (open_owned). Градация разыгрывается в
момент открытия с шансами по дню стрика, за который ларец выдан.

ЖЁСТКОЕ ПРАВИЛО: ларец нельзя купить — ни за золото, ни за самоцветы, ни за
реальные деньги. Не подключать эту механику ни к одному платному пути
(магазин/донат-офферы/биржа). Входы - только бесплатные награды: стрик
ежедневок (daily_service._finish), торговля и путешествия (trade_service,
voyage_service), выдача админом и промокоды владельца (admin_grant_service,
promo_service).
"""

import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot import raid_key_texts
from game.content_loader import LootboxGradeDef, LootboxRewardPart, load_lootbox_grades
from game.economy import dailies_config as dc
from game.economy import lootbox_config as lc
from game.economy import mining
from models import Character, CharacterLootbox
from services import elixir_service, mining_service, raid_key_service, trophy_service, wallet_service

ASHEN, ORE, SUPPLY = "ashen", "ore", "supply"


@dataclass(frozen=True)
class ChestKind:
    file: str
    name: str
    icon: str
    description: str


#: Виды ларцов (2026-10-13: ларцы кровавого разлома). Градации у каждого
#: свои - content/lootbox/<file>.json; ids градаций общие (dusty..tear),
#: от них цвет карточек рулетки.
CHEST_KINDS: dict[str, ChestKind] = {
    ASHEN: ChestKind("ashen_chest", "Пепельный ларец", "chest:dusty",
                     "Ларец за день серии ежедневок. Что внутри - решает рулетка при открытии."),
    ORE: ChestKind("ore_chest", "Ларец руды", "chest:ore",
                   "Добыча кровавого разлома: 1-3 руды, чем реже карточка - тем ценнее руда."),
    SUPPLY: ChestKind("supply_chest", "Ларец расходников", "chest:supply",
                      "Добыча кровавого разлома: 1-3 зелья, а с самой редкой карточки - свиток, "
                      "которого больше нигде не достать."),
}

_grades: dict[str, list[LootboxGradeDef]] = {}


def _load(kind: str = ASHEN) -> list[LootboxGradeDef]:
    if kind not in _grades:
        _grades[kind] = load_lootbox_grades(name=CHEST_KINDS[kind].file)
    return _grades[kind]


def grade_catalog(kind: str = ASHEN) -> list[LootboxGradeDef]:
    """Все градации в порядке содержимого файла (для мини-аппа: подписи к
    счётчику "по градациям за всё время")."""
    return _load(kind)


def _chances(daily_streak: int, kind: str = ASHEN) -> dict[str, float]:
    grades = _load(kind)
    chances = {g.id: g.chance for g in grades}
    # Буст от стрика ежедневок - только у Пепельного: он и выдаётся за стрик.
    if kind != ASHEN or not lc.STREAK_CHANCE_BOOST_ENABLED:
        return chances
    mult = lc.boost_multiplier(daily_streak)
    if mult == 1.0:
        return chances
    increase_total = 0.0
    for gid in lc.BOOSTED_GRADES:
        boosted = chances[gid] * mult
        increase_total += boosted - chances[gid]
        chances[gid] = boosted
    chances["dusty"] = max(0.0, chances["dusty"] - increase_total)
    return chances


def roll_grade(rng: random.Random, daily_streak: int, kind: str = ASHEN) -> LootboxGradeDef:
    chances = _chances(daily_streak, kind)
    grades = _load(kind)
    total = sum(chances.values())
    roll = rng.uniform(0, total)
    cumulative = 0.0
    for g in grades:
        cumulative += chances[g.id]
        if roll < cumulative:
            return g
    return grades[-1]


async def _apply_part(db: AsyncSession, character: Character, part: LootboxRewardPart, rng: random.Random) -> str:
    if part.type == "gold":
        amount = rng.randint(part.min, part.max)
        await wallet_service.deposit(db, character.id, "farm", amount)
        from services import guild_service

        return guild_service.gold_label(character, amount)
    if part.type == "gems":
        amount = rng.randint(part.min, part.max)
        await wallet_service.deposit(db, character.id, "donate", amount)
        return f"💎 {amount} Пепельных самоцветов"
    if part.type == "elixir":
        amount = rng.randint(part.min, part.max)
        await elixir_service.grant(db, character.id, part.elixir_id, amount)
        edef = elixir_service.elixir_def(part.elixir_id)
        name = f"{edef.emoji} {edef.name}" if edef is not None else part.elixir_id
        return f"{name} ×{amount}"
    if part.type == "elixir_random_combat":
        count = min(rng.randint(part.min, part.max), len(dc.COMBAT_ELIXIR_POOL))
        chosen = rng.sample(dc.COMBAT_ELIXIR_POOL, count)
        names = []
        for elixir_id in chosen:
            await elixir_service.grant(db, character.id, elixir_id, 1)
            edef = elixir_service.elixir_def(elixir_id)
            names.append(f"{edef.emoji} {edef.name}" if edef is not None else elixir_id)
        return ", ".join(names)
    if part.type == "ore":
        # Качество - как у добытчика этого игрока в руднике того же тира.
        amount = rng.randint(part.min, part.max)
        ore = mining.ore_def(part.ore_id)
        grade_id, grade_title = mining.roll_grade(rng, ore.tier if ore else 1, character.mining_level or 1)
        await mining_service.add_ore(db, character.id, part.ore_id, grade_id, amount)
        name = f"{ore.emoji} {ore.name}" if ore is not None else part.ore_id
        return f"{name} ({grade_title}) ×{amount}"
    if part.type == "trophy":
        amount = rng.randint(part.min, part.max)
        await trophy_service.grant_specific(db, character.id, part.trophy_id, amount)
        tdef = trophy_service.trophy_def(part.trophy_id)
        name = f"{tdef.emoji} {tdef.name}" if tdef is not None else part.trophy_id
        return f"{name} ×{amount}"
    raise ValueError(f"unknown lootbox reward type: {part.type}")


@dataclass
class LootboxOpenResult:
    grade: LootboxGradeDef
    lines: list[str]
    kind: str = ASHEN
    option: list[LootboxRewardPart] | None = None


async def _roll_and_apply(
    db: AsyncSession, character: Character, daily_streak: int, rng: random.Random, kind: str = ASHEN,
) -> LootboxOpenResult:
    grade = roll_grade(rng, daily_streak, kind)
    option = rng.choice(grade.options)
    lines = [await _apply_part(db, character, part, rng) for part in option]
    # Ключ Монолита - шанс только Пепельного ларца.
    if kind == ASHEN and await raid_key_service.maybe_grant(db, character, rng):
        lines.append(raid_key_texts.RAID_KEY_NAME)
    return LootboxOpenResult(grade=grade, lines=lines, kind=kind, option=option)


async def open_chest(
    db: AsyncSession, character: Character, daily_streak: int, rng: random.Random,
) -> LootboxOpenResult:
    """Выдать и сразу открыть (история, тесты шансов). В игре ларец идёт
    через grant_chest -> open_owned."""
    result = await _roll_and_apply(db, character, daily_streak, rng)
    db.add(CharacterLootbox(
        character_id=character.id, status="opened", streak=daily_streak, grade=result.grade.id,
        reward_summary="; ".join(result.lines)[:256], opened_at=func.now(),
    ))
    await db.flush()
    return result


# --- Ларец в сумке (патч 106) -------------------------------------------------

CHEST_NAME = "Пепельный ларец"
CHEST_ICON = "chest:dusty"


async def grant_chest(
    db: AsyncSession, character: Character, daily_streak: int, kind: str = ASHEN,
) -> CharacterLootbox:
    chest = CharacterLootbox(character_id=character.id, status="closed", streak=daily_streak, kind=kind)
    db.add(chest)
    await db.flush()
    return chest


async def closed_chests(db: AsyncSession, character_id: int, kind: str | None = None) -> list[CharacterLootbox]:
    query = select(CharacterLootbox).where(
        CharacterLootbox.character_id == character_id, CharacterLootbox.status == "closed",
    )
    if kind is not None:
        query = query.where(CharacterLootbox.kind == kind)
    return list((await db.scalars(query.order_by(CharacterLootbox.id))).all())


class ChestGone(Exception):
    """Ларца нет или он уже открыт (двойное нажатие, другая вкладка)."""


async def open_owned(
    db: AsyncSession, character: Character, chest_id: int | None, rng: random.Random, kind: str = ASHEN,
) -> tuple[CharacterLootbox, LootboxOpenResult]:
    """Открывает закрытый ларец персонажа (chest_id=None - самый старый
    ларец вида kind).

    Сначала условный UPDATE closed -> opened: два нажатия «Открыть» не
    откроют один ларец дважды - второе не найдёт закрытого."""
    if chest_id is None:
        chests = await closed_chests(db, character.id, kind)
        if not chests:
            raise ChestGone()
        chest_id = chests[0].id
    claimed = await db.execute(
        update(CharacterLootbox).where(
            CharacterLootbox.id == chest_id,
            CharacterLootbox.character_id == character.id,
            CharacterLootbox.status == "closed",
        ).values(status="opened", opened_at=func.now())
        .execution_options(synchronize_session="fetch")
    )
    if not claimed.rowcount:
        raise ChestGone()
    chest = await db.get(CharacterLootbox, chest_id)
    result = await _roll_and_apply(
        db, character, chest.streak or character.daily_streak, rng, chest.kind or ASHEN,
    )
    chest.grade = result.grade.id
    chest.reward_summary = "; ".join(result.lines)[:256]
    await db.flush()
    return chest, result


# --- Лента рулетки ----------------------------------------------------------------


def _part_preview(part: LootboxRewardPart) -> str:
    span = f"{part.min}" if part.min == part.max else f"{part.min}-{part.max}"
    if part.type == "gold":
        return f"{span} золота"
    if part.type == "gems":
        return f"💎 {span} самоцветов"
    if part.type == "elixir":
        edef = elixir_service.elixir_def(part.elixir_id)
        return f"{edef.name if edef else part.elixir_id} ×{span}"
    if part.type == "elixir_random_combat":
        return f"Боевые эликсиры ×{span}"
    if part.type == "trophy":
        tdef = trophy_service.trophy_def(part.trophy_id)
        return f"{tdef.name if tdef else part.trophy_id} ×{span}"
    if part.type == "ore":
        ore = mining.ore_def(part.ore_id)
        return f"{ore.name if ore else part.ore_id} ×{span}"
    return part.type


def _card_icon(grade: LootboxGradeDef, kind: str, option: list[LootboxRewardPart] | None) -> str:
    """Карточка ленты - сам ларец, а не добыча: у Пепельного - ларец своей
    градации, у ларцов разлома - картинка ларца этого вида (цвет градации
    даёт рамка карточки). Добыча показывается только при вскрытии."""
    if kind != ASHEN:
        return CHEST_KINDS[kind].icon
    return f"chest:{grade.id}"


def _card(grade: LootboxGradeDef, label: str, kind: str = ASHEN,
          option: list[LootboxRewardPart] | None = None) -> dict:
    # Подпись карточки - название градации по Пепельному ларцу (Пыльный,
    # Тусклый...): у ларцов разлома своё имя градации - это имя руды.
    tier = next((g.name for g in _load(ASHEN) if g.id == grade.id), grade.name)
    return {"grade": grade.id, "grade_name": tier, "icon": _card_icon(grade, kind, option), "label": label}


ROULETTE_LENGTH = 44
ROULETTE_WIN_INDEX = 38


def roulette_strip(result: LootboxOpenResult, daily_streak: int, rng: random.Random) -> tuple[list[dict], int]:
    kind = result.kind
    """Лента карточек для рулетки и место выигрыша в ней.

    Карточки-обманки тянутся с теми же шансами, что настоящий ролл: чаще
    всего мелькают пыльные, изредка - раскалённые. Выигрышная стоит на
    ROULETTE_WIN_INDEX; клиент докручивает ленту ровно до неё. Исход уже
    решён сервером - рулетка его только показывает."""
    strip = []
    for _ in range(ROULETTE_LENGTH):
        grade = roll_grade(rng, daily_streak, kind)
        option = rng.choice(grade.options)
        strip.append(_card(grade, ", ".join(_part_preview(p) for p in option), kind, option))
    strip[ROULETTE_WIN_INDEX] = _card(result.grade, ", ".join(result.lines), kind, result.option)
    return strip, ROULETTE_WIN_INDEX


@dataclass
class LootboxHistoryEntry:
    grade: str
    emoji: str
    name: str
    reward_summary: str
    opened_at: datetime


async def recent_history(db: AsyncSession, character_id: int, limit: int = 10) -> list[LootboxHistoryEntry]:
    rows = (
        await db.execute(
            select(CharacterLootbox)
            .where(CharacterLootbox.character_id == character_id, CharacterLootbox.status == "opened",
                   CharacterLootbox.kind == ASHEN)
            .order_by(CharacterLootbox.opened_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    grade_defs = {g.id: g for g in _load()}
    return [
        LootboxHistoryEntry(
            grade=r.grade,
            emoji=grade_defs[r.grade].emoji if r.grade in grade_defs else "",
            name=grade_defs[r.grade].name if r.grade in grade_defs else r.grade,
            reward_summary=r.reward_summary or "",
            opened_at=r.opened_at,
        )
        for r in rows
    ]


async def grade_counts(db: AsyncSession, character_id: int) -> dict[str, int]:
    """{grade_id: count} за всё время, только градации с count > 0."""
    rows = (
        await db.execute(
            select(CharacterLootbox.grade, func.count())
            .where(CharacterLootbox.character_id == character_id, CharacterLootbox.status == "opened",
                   CharacterLootbox.kind == ASHEN)
            .group_by(CharacterLootbox.grade)
        )
    ).all()
    return {grade: count for grade, count in rows}
