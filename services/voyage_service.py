"""Долгие путешествия (AFK): покупка, улучшения, поход, ежечасные события.

Числа и тексты - game/economy/voyage_config.py. Сервис не шлёт сообщений:
tick() возвращает, что сказать и кому, - как crown_service и др.
Начать можно только в родном городе (character.region); персонаж на время
похода остаётся на клетке города, но из игры выключен: обработчик
bot/handlers/voyage.py перехватывает всё, кроме «Вернуться».
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import voyage_config as vc
from game.world import grid
from models import Character, CharacterStats, CharacterVoyage
from services import experience_service, lootbox_service, trophy_service, wallet_service


class VoyageError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def get(db: AsyncSession, character_id: int, lock: bool = False) -> CharacterVoyage | None:
    query = select(CharacterVoyage).where(CharacterVoyage.character_id == character_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def away_ids(db: AsyncSession) -> set[int]:
    return set((await db.scalars(
        select(CharacterVoyage.character_id).where(CharacterVoyage.status == "away")
    )).all())


def voyage_of(character: Character) -> vc.Voyage | None:
    return vc.VOYAGES.get(character.region or "")


def part_value(voyage: CharacterVoyage, part_id: str):
    return vc.PARTS_BY_ID[part_id].values[getattr(voyage, part_id) - 1]


def upgrade_cost(voyage: CharacterVoyage, part_id: str) -> int | None:
    part = vc.PARTS_BY_ID[part_id]
    level = getattr(voyage, part_id)
    return part.costs[level - 1] if level < len(part.values) else None


def _in_home_city(character: Character) -> bool:
    return character.region is not None and grid.city_region_at(character.pos_x, character.pos_y) == character.region


def _require_home(character: Character) -> vc.Voyage:
    trip = voyage_of(character)
    if trip is None or not _in_home_city(character):
        raise VoyageError("Долгий путь начинается только в родном городе.")
    return trip


async def buy(db: AsyncSession, character: Character) -> CharacterVoyage:
    trip = _require_home(character)
    if character.level < vc.VOYAGE_MIN_LEVEL:
        raise VoyageError(f"В долгий путь отпускают с {vc.VOYAGE_MIN_LEVEL} уровня.")
    if await get(db, character.id) is not None:
        raise VoyageError(f"{trip.gear} у тебя уже есть.")
    try:
        await wallet_service.charge(db, character.id, "farm", vc.VOYAGE_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise VoyageError(f"{trip.gear}: {vc.VOYAGE_PRICE} золота.") from None
    voyage = CharacterVoyage(
        character_id=character.id, region=character.region, endurance=1, haul=1, guide=1,
        status="home", hours_done=0, trip_xp=0, trip_gold=0, voyages_total=0,
    )
    db.add(voyage)
    await db.flush()
    return voyage


async def upgrade(db: AsyncSession, character: Character, part_id) -> CharacterVoyage:
    _require_home(character)
    if part_id not in vc.PARTS_BY_ID:
        raise VoyageError("Нет такой части.")
    voyage = await get(db, character.id, lock=True)
    if voyage is None:
        raise VoyageError("Сначала нужно снаряжение.")
    if voyage.status == "away":
        raise VoyageError("Ты в пути.")
    cost = upgrade_cost(voyage, part_id)
    if cost is None:
        raise VoyageError("Улучшено до предела.")
    try:
        await wallet_service.charge(db, character.id, "farm", cost)
    except wallet_service.NotEnoughCurrency:
        raise VoyageError(f"Нужно {cost} золота.") from None
    setattr(voyage, part_id, getattr(voyage, part_id) + 1)
    await db.flush()
    return voyage


async def start(db: AsyncSession, character: Character, now: datetime | None = None) -> CharacterVoyage:
    """Уйти в путь. Проверки боя/занятости - на вызывающем (там живые реестры)."""
    _require_home(character)
    now = now or _now()
    voyage = await get(db, character.id, lock=True)
    if voyage is None:
        raise VoyageError("Сначала нужно снаряжение.")
    if voyage.status == "away":
        raise VoyageError("Ты уже в пути.")
    from services import death_service, mount_service, movement_service

    if death_service.is_dead(character, now):
        raise VoyageError("☠ Сначала очнись.")
    if movement_service.is_traveling(character, now) or await mount_service.active_travel(db, character.id):
        raise VoyageError("Ты в дороге.")
    hours = part_value(voyage, "endurance")
    voyage.status = "away"
    voyage.region = character.region
    voyage.started_at = now
    voyage.ends_at = now + timedelta(hours=hours)
    voyage.next_event_at = now + timedelta(minutes=vc.EVENT_INTERVAL_MINUTES)
    voyage.hours_done = 0
    voyage.trip_xp = 0
    voyage.trip_gold = 0
    await db.flush()
    return voyage


def total_hours(voyage: CharacterVoyage) -> int:
    started, ends = _aware(voyage.started_at), _aware(voyage.ends_at)
    if started is None or ends is None:
        return part_value(voyage, "endurance")
    return round((ends - started).total_seconds() / 3600)


# --- События ---


def _roll_event(voyage: CharacterVoyage, rng: random.Random) -> tuple[str, int, str, str]:
    """(тир, номер, текст, тип награды); то же событие подряд не выпадает."""
    trip = vc.VOYAGES[voyage.region]
    guide = part_value(voyage, "guide")
    weights = {
        tier: w * (guide if tier in ("rare", "legendary") else 1.0)
        for tier, w in vc.TIER_WEIGHTS.items()
    }
    tier = rng.choices(list(weights), weights=list(weights.values()))[0]
    pool = trip.events[tier]
    options = [i for i in range(len(pool)) if f"{tier}:{i}" != voyage.last_event] or list(range(len(pool)))
    index = rng.choice(options)
    text, kind = pool[index]
    return tier, index, text, kind


async def _reward(
    db: AsyncSession, character: Character, stats: CharacterStats, voyage: CharacterVoyage, kind: str,
) -> tuple[list[str], int, int, int]:
    """Начисляет награду события. (строки, опыт, золото, новых уровней)."""
    haul = 1 + part_value(voyage, "haul") / 100
    lines, xp, gold, levels = [], 0, 0, 0
    if kind in vc.XP_MOBS:
        amount = round(experience_service.xp_per_mob(character.level) * vc.XP_MOBS[kind] * haul)
        up = experience_service.add_experience(character, stats, amount)
        xp, levels = up.xp_awarded, up.levels_gained
        if xp:
            lines.append(f"+{xp} опыта")
    if kind in vc.GOLD_BASE:
        gold = round(vc.GOLD_BASE[kind] * (1 + character.level / 30) * haul)
        await wallet_service.deposit(db, character.id, "farm", gold)
        lines.append(f"+{gold} золота")
    if kind in vc.TROPHY_OF:
        trophy_id, count = vc.TROPHY_OF[kind]
        await trophy_service.grant_specific(db, character.id, trophy_id, count)
        trophy = trophy_service.trophy_def(trophy_id)
        lines.append(f"{trophy.emoji} {trophy.name}" + (f" ×{count}" if count > 1 else ""))
    if kind == "chest":
        await lootbox_service.grant_chest(db, character, 0)
        lines.append(f"🎁 {lootbox_service.CHEST_NAME}")
    return lines, xp, gold, levels


@dataclass
class Notice:
    character_id: int
    text: str
    finished: bool = False
    levels: int = 0
    new_level: int = 0


async def tick(db: AsyncSession, rng: random.Random | None = None, now: datetime | None = None) -> list[Notice]:
    """Все, у кого подошло время: событие (по одному за каждый прошедший час -
    после простоя бота догоняются все) и конец похода по запасу хода."""
    rng = rng or random.Random()
    now = now or _now()
    rows = (await db.scalars(
        select(CharacterVoyage).where(CharacterVoyage.status == "away", CharacterVoyage.next_event_at <= now)
        .with_for_update()
    )).all()
    notices: list[Notice] = []
    for voyage in rows:
        character = await db.get(Character, voyage.character_id)
        stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == voyage.character_id))
        if character is None or stats is None:
            continue
        hours = total_hours(voyage)
        while voyage.status == "away" and _aware(voyage.next_event_at) <= now:
            tier, index, text, kind = _roll_event(voyage, rng)
            voyage.last_event = f"{tier}:{index}"
            lines, xp, gold, levels = await _reward(db, character, stats, voyage, kind)
            voyage.hours_done += 1
            voyage.trip_xp += xp
            voyage.trip_gold += gold
            trip = vc.VOYAGES[voyage.region]
            body = f"{trip.emoji} Час {voyage.hours_done} из {hours}. {vc.TIER_TITLES[tier]}{text}"
            if lines:
                body += "\n" + " · ".join(lines)
            notices.append(Notice(character.id, body, levels=levels, new_level=character.level))
            voyage.next_event_at = _aware(voyage.next_event_at) + timedelta(minutes=vc.EVENT_INTERVAL_MINUTES)
            if voyage.hours_done >= hours or voyage.next_event_at > _aware(voyage.ends_at) + timedelta(seconds=1):
                notices.append(Notice(character.id, _finish(voyage, early=False), finished=True))
    await db.flush()
    return notices


def _finish(voyage: CharacterVoyage, early: bool) -> str:
    trip = vc.VOYAGES[voyage.region]
    summary = f"За поход: +{voyage.trip_xp} опыта, +{voyage.trip_gold} золота, событий {voyage.hours_done}."
    voyage.status = "home"
    voyage.next_event_at = None
    voyage.voyages_total += 1
    return f"{trip.back_early if early else trip.finish}\n\n{summary}"


async def come_back(db: AsyncSession, character: Character) -> str:
    """Вернуться раньше времени. Награды за прошедшие часы уже начислены."""
    voyage = await get(db, character.id, lock=True)
    if voyage is None or voyage.status != "away":
        raise VoyageError("Ты не в пути.")
    text = _finish(voyage, early=True)
    await db.flush()
    return text
