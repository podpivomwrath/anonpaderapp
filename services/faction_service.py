"""Процветание фракций (городов): очки, падение, вклад торговцев, цены
лавки и скупщика по ступени. Числа - game/economy/faction_config.py."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import faction_config as fc
from game.world import grid
from models import Character, FactionState, TradeContribution

MSK = timezone(timedelta(hours=3))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def msk_day(now: datetime) -> date:
    return now.astimezone(MSK).date()


def decayed(points: float, since: datetime, now: datetime) -> float:
    days = max((now - _aware(since)).total_seconds() / 86400, 0.0)
    return points * (1 - fc.DECAY_PER_DAY) ** days


async def _row(db: AsyncSession, city: str, now: datetime, lock: bool) -> FactionState:
    query = select(FactionState).where(FactionState.city == city)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        row = FactionState(city=city, points=float(fc.START_POINTS), updated_at=now)
        db.add(row)
        await db.flush()
    return row


async def points(db: AsyncSession, now: datetime | None = None) -> dict[str, float]:
    """Очки всех городов сейчас (падение считается, в базу не пишется)."""
    now = now or _now()
    rows = {r.city: r for r in (await db.scalars(select(FactionState))).all()}
    return {
        city: decayed(rows[city].points, rows[city].updated_at, now) if city in rows else float(fc.START_POINTS)
        for city in fc.CITIES
    }


async def tier_of(db: AsyncSession, city: str | None, now: datetime | None = None) -> fc.Tier | None:
    if city is None:
        return None
    return fc.tier_for((await points(db, now))[city])


async def add_points(db: AsyncSession, city: str, amount: float, now: datetime | None = None) -> float:
    now = now or _now()
    row = await _row(db, city, now, lock=True)
    row.points = min(decayed(row.points, row.updated_at, now) + amount, float(fc.MAX_POINTS))
    row.updated_at = now
    return row.points


async def contribute(
    db: AsyncSession, character: Character, trade_level: int, raw: int, now: datetime | None = None,
) -> int:
    """Вклад торговца в процветание РОДНОГО города: raw очков за проданные
    ящики, засчитывается не больше дневного потолка. Возвращает засчитанное."""
    if raw <= 0 or character.region not in fc.CITIES:
        return 0
    now = now or _now()
    day = msk_day(now)
    row = await db.scalar(
        select(TradeContribution).where(
            TradeContribution.character_id == character.id, TradeContribution.day == day,
        ).with_for_update().execution_options(populate_existing=True)
    )
    if row is None:
        row = TradeContribution(character_id=character.id, day=day, city=character.region, points=0, raw=0)
        db.add(row)
    credited = max(min(raw, fc.daily_cap(trade_level) - (row.points or 0)), 0)
    row.points = (row.points or 0) + credited
    row.raw = (row.raw or 0) + raw
    await db.flush()
    if credited:
        await add_points(db, character.region, credited, now)
    return credited


async def today_points(db: AsyncSession, character_id: int, now: datetime | None = None) -> int:
    row = await db.get(TradeContribution, (character_id, msk_day(now or _now())))
    return row.points if row is not None else 0


async def _city_tier_here(db: AsyncSession, character: Character) -> fc.Tier | None:
    return await tier_of(db, grid.city_region_at(character.pos_x, character.pos_y))


async def shop_mult(db: AsyncSession, character: Character) -> float:
    """Множитель цены зелий в лавке: Пепельное клеймо x ступень города."""
    from services import pk_service

    tier = await _city_tier_here(db, character)
    return pk_service.shop_mult(character) * (tier.elixir_mult if tier else 1.0)


async def relic_mult(db: AsyncSession, character: Character) -> float:
    """Множитель выручки за реликвии: Пепельное клеймо x ступень города."""
    from services import pk_service

    tier = await _city_tier_here(db, character)
    return pk_service.relic_mult(character) * (tier.relic_mult if tier else 1.0)


async def city_line(db: AsyncSession, character: Character, relics: bool) -> str:
    """Строка для лавки/скупщика: ступень города и что она даёт. Пусто в Застое."""
    tier = await _city_tier_here(db, character)
    if tier is None:
        return ""
    mult = tier.relic_mult if relics else tier.elixir_mult
    if mult == 1.0:
        return ""
    pct = round((mult - 1) * 100)
    what = "за реликвии" if relics else "на зелья"
    return f"{tier.emoji} {tier.name} города: {pct:+d}% {what}."
