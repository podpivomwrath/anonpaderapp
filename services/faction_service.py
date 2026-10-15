"""Процветание фракций (городов): очки, падение, вклад торговцев, цены
лавки и скупщика по ступени. Числа - game/economy/faction_config.py."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import faction_config as fc
from game.world import grid
from models import Character, FactionPayout, FactionState, FactionWeek, TradeContribution

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


# --- Неделя фракции (этап 2) ---


def week_start(day: date) -> date:
    """Понедельник недели (по Москве), в которую входит day."""
    return day - timedelta(days=day.weekday())


async def week_top(db: AsyncSession, city: str, start: date, limit: int = 3) -> list[tuple[int, str, int]]:
    """Лучшие поставщики фракции за неделю с start: (character_id, имя, очки
    без дневного потолка)."""
    total = func.sum(TradeContribution.raw)
    rows = (await db.execute(
        select(TradeContribution.character_id, Character.name, total)
        .join(Character, Character.id == TradeContribution.character_id)
        .where(
            TradeContribution.city == city, TradeContribution.day >= start,
            TradeContribution.day < start + timedelta(days=7),
        )
        .group_by(TradeContribution.character_id, Character.name)
        .having(total > 0)
        .order_by(total.desc(), TradeContribution.character_id)
        .limit(limit)
    )).all()
    return [(cid, name, int(raw)) for cid, name, raw in rows]


async def first_supplier(db: AsyncSession, city: str | None, now: datetime | None = None) -> int | None:
    """Первый поставщик фракции на эту неделю - победитель последней
    закрытой недели (её начало раньше начала текущей)."""
    if city not in fc.CITIES:
        return None
    current = week_start(msk_day(now or _now()))
    row = await db.scalar(
        select(FactionWeek).where(FactionWeek.city == city, FactionWeek.week_start == current - timedelta(days=7))
    )
    return row.first_id if row is not None else None


@dataclass
class WeekAward:
    character_id: int
    city: str
    place: int
    chests: dict


async def close_week(db: AsyncSession, now: datetime | None = None) -> list[WeekAward]:
    """Итог прошлой недели по каждой фракции: тройка лучших, ларцы, первый
    поставщик. Повторный вызов ничего не делает (строка недели уже есть)."""
    from game.economy import trade_config as tc
    from services import lootbox_service

    now = now or _now()
    start = week_start(msk_day(now)) - timedelta(days=7)
    awards: list[WeekAward] = []
    for city in fc.CITIES:
        if await db.get(FactionWeek, (city, start)) is not None:
            continue
        top = await week_top(db, city, start)
        ids = [cid for cid, _, _ in top] + [None, None, None]
        db.add(FactionWeek(city=city, week_start=start, first_id=ids[0], second_id=ids[1], third_id=ids[2]))
        for place, (cid, _, _) in enumerate(top, 1):
            character = await db.get(Character, cid)
            chests = tc.WEEK_REWARDS[place]
            for kind, n in chests.items():
                for _ in range(n):
                    await lootbox_service.grant_chest(db, character, 0, kind=kind)
            awards.append(WeekAward(cid, city, place, chests))
        await db.flush()
    return awards


# --- Налог на переводы (этап 3) ---


async def tax_transfer(
    db: AsyncSession, recipient_id: int, currency: str, amount: int, now: datetime | None = None,
) -> tuple[int, str | None]:
    """Налог с перевода валюты (currency: farm|donate) получателю. Возвращает
    (налог, город получателя). Доля первого поставщика фракции получателя
    копится в faction_payouts; остальное уходит из игры."""
    tax = fc.transfer_tax(amount)
    recipient = await db.get(Character, recipient_id)
    city = recipient.region if recipient is not None and recipient.region in fc.CITIES else None
    if tax <= 0 or city is None:
        return tax, city
    share = fc.leader_share(tax)
    leader = await first_supplier(db, city, now)
    if share > 0 and leader is not None:
        row = await db.scalar(
            select(FactionPayout).where(FactionPayout.character_id == leader)
            .with_for_update().execution_options(populate_existing=True)
        )
        if row is None:
            row = FactionPayout(character_id=leader, gold=0, gems=0)
            db.add(row)
        if currency == "farm":
            row.gold = (row.gold or 0) + share
        else:
            row.gems = (row.gems or 0) + share
        await db.flush()
    return tax, city


@dataclass
class Payout:
    character_id: int
    gold: int
    gems: int


async def pay_leaders(db: AsyncSession) -> list[Payout]:
    """Раз в сутки: накопленные доли налога - первым поставщикам."""
    from services import wallet_service

    out = []
    rows = (await db.scalars(
        select(FactionPayout).where((FactionPayout.gold > 0) | (FactionPayout.gems > 0))
        .with_for_update().execution_options(populate_existing=True)
    )).all()
    for row in rows:
        gold, gems = int(row.gold or 0), int(row.gems or 0)
        if gold:
            await wallet_service.deposit(db, row.character_id, "farm", gold)
        if gems:
            await wallet_service.deposit(db, row.character_id, "donate", gems)
        row.gold = row.gems = 0
        out.append(Payout(row.character_id, gold, gems))
    await db.flush()
    return out
