"""Биржа самоцветов: игра - дилер, курс по формуле game/economy/exchange.py.

Торгуют только лотами по EXCHANGE_BLOCK_SIZE (100) самоцветов. Курс - от
чистого объёма, проданного игрокам: покупки поднимают цену лота, продажи
опускают. Покупка и продажа на одной ступени расходятся на спред, поэтому
«купить и сразу продать» всегда в минус.

Курс живёт строкой exchange_state и берётся под блокировкой на всю сделку:
два одновременных лота не пройдут по одной цене.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy.exchange import Exchange
from models import Character, ExchangeDaily, ExchangeOrder, ExchangeState, OrderDirection
from services import wallet_service

LOT = bc.EXCHANGE_BLOCK_SIZE
MAX_LOTS = 50


class ExchangeError(Exception):
    """Отказ с готовым текстом для игрока."""


class DbExchangeState:
    """Состояние курса в базе. get_net_sold берёт строку под блокировкой -
    она держится до конца транзакции сделки."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _row(self) -> ExchangeState:
        row = await self._db.scalar(
            select(ExchangeState).where(ExchangeState.id == 1).with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            row = ExchangeState(id=1, net_sold=0)
            self._db.add(row)
            await self._db.flush()
        return row

    async def get_net_sold(self) -> int:
        return (await self._row()).net_sold

    async def add_net_sold(self, delta: int) -> int:
        row = await self._row()
        row.net_sold += delta
        await self._db.flush()
        return row.net_sold


@dataclass
class Quote:
    net_sold: int
    #: Цена ОДНОГО следующего лота при покупке и продаже.
    buy_lot: int
    sell_lot: int
    #: Цены N лотов подряд: курс сдвигается с каждым лотом.
    buy_series: list[int]
    sell_series: list[int]


async def quote(db: AsyncSession, lots: int = 10) -> Quote:
    net = await DbExchangeState(db).get_net_sold()
    buy = [Exchange.buy_cost(net, LOT * n) for n in range(1, lots + 1)]
    sell = [Exchange.sell_gain(net, LOT * n) for n in range(1, lots + 1)]
    return Quote(net, buy[0], sell[0], buy, sell)


def _check_lots(lots: int) -> None:
    if not isinstance(lots, int) or isinstance(lots, bool) or not 1 <= lots <= MAX_LOTS:
        raise ExchangeError(f"Самоцветы торгуются лотами по {LOT}: от 1 до {MAX_LOTS} лотов за раз.")


async def buy(db: AsyncSession, character: Character, lots: int) -> ExchangeOrder:
    _check_lots(lots)
    exchange = Exchange(DbExchangeState(db))
    try:
        order = await exchange.buy_donate(db, character.id, lots * LOT)
    except wallet_service.NotEnoughCurrency:
        cost = Exchange.buy_cost(await DbExchangeState(db).get_net_sold(), lots * LOT)
        raise ExchangeError(f"Не хватает золота: {lots * LOT} 💎 стоят {cost}.") from None
    await db.flush()
    return order


async def sell(db: AsyncSession, character: Character, lots: int) -> ExchangeOrder:
    _check_lots(lots)
    exchange = Exchange(DbExchangeState(db))
    try:
        order = await exchange.sell_donate(db, character.id, lots * LOT)
    except wallet_service.NotEnoughCurrency:
        raise ExchangeError(f"Не хватает самоцветов: нужно {lots * LOT} 💎.") from None
    await db.flush()
    return order


async def my_orders(db: AsyncSession, character_id: int, limit: int = 15) -> list[ExchangeOrder]:
    return list(
        (
            await db.scalars(
                select(ExchangeOrder).where(ExchangeOrder.character_id == character_id)
                .order_by(ExchangeOrder.created_at.desc(), ExchangeOrder.id.desc()).limit(limit)
            )
        ).all()
    )


async def recent_orders(db: AsyncSession, limit: int = 40) -> list[ExchangeOrder]:
    return list(
        (
            await db.scalars(
                select(ExchangeOrder).order_by(ExchangeOrder.created_at.desc(), ExchangeOrder.id.desc()).limit(limit)
            )
        ).all()
    )


def is_buy(order: ExchangeOrder) -> bool:
    return order.direction == OrderDirection.BUY


# --- График: курс на закрытие дня ----------------------------------------------

_TZ = ZoneInfo("Europe/Moscow")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=_TZ)
    return start, start + timedelta(days=1)


async def snapshot_day(db: AsyncSession, day: date) -> ExchangeDaily:
    """Курс на конец дня day (МСК) и объём сделок за день. Курс на конец дня
    - текущий, отмотанный назад на сделки, прошедшие после полуночи: задача
    бежит чуть позже полуночи, и сделки этих минут в прошлый день не идут."""
    start, end = _day_bounds(day)
    net = await DbExchangeState(db).get_net_sold()
    later = (await db.scalars(select(ExchangeOrder).where(ExchangeOrder.created_at >= end))).all()
    for order in later:
        net -= order.amount if order.direction == OrderDirection.BUY else -order.amount
    orders = (
        await db.scalars(
            select(ExchangeOrder).where(ExchangeOrder.created_at >= start, ExchangeOrder.created_at < end)
        )
    ).all()
    level = Exchange._lot_of(net)
    row = await db.get(ExchangeDaily, day)
    if row is None:
        row = ExchangeDaily(day=day, buy_lot=0, sell_lot=0)
        db.add(row)
    row.buy_lot = Exchange.lot_buy_price(level)
    row.sell_lot = Exchange.lot_sell_price(level)
    row.bought_lots = sum(o.amount for o in orders if o.direction == OrderDirection.BUY) // LOT
    row.sold_lots = sum(o.amount for o in orders if o.direction != OrderDirection.BUY) // LOT
    await db.flush()
    return row


async def daily_chart(db: AsyncSession, days: int = 60) -> list[ExchangeDaily]:
    return list(
        reversed(
            (await db.scalars(select(ExchangeDaily).order_by(ExchangeDaily.day.desc()).limit(days))).all()
        )
    )


def yesterday_msk() -> date:
    return datetime.now(_TZ).date() - timedelta(days=1)



def today_start_msk() -> datetime:
    return datetime.combine(datetime.now(_TZ).date(), time.min, tzinfo=_TZ)


async def chart_points(db: AsyncSession, days: int = 14) -> list[dict]:
    """Точки графика: каждая сделка (курс сразу после неё) и закрытие каждого
    дня - только по ЗАКРЫТЫМ дням: график обновляется раз в сутки.

    Курс в сделке не хранится - он восстанавливается обратным ходом от
    текущего объёма: покупка сдвинула его вверх, продажа - вниз."""
    cutoff = today_start_msk()
    since = cutoff - timedelta(days=days)
    net = await DbExchangeState(db).get_net_sold()
    orders = (
        await db.scalars(
            select(ExchangeOrder).where(ExchangeOrder.created_at >= since)
            .order_by(ExchangeOrder.created_at.desc(), ExchangeOrder.id.desc())
        )
    ).all()
    points = []
    for order in orders:
        created = order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)
        if created < cutoff:
            level = Exchange._lot_of(net)
            points.append({
                "t": created.isoformat(), "kind": "buy" if order.direction == OrderDirection.BUY else "sell",
                "lots": order.amount // LOT, "buy": Exchange.lot_buy_price(level), "sell": Exchange.lot_sell_price(level),
            })
        net -= order.amount if order.direction == OrderDirection.BUY else -order.amount
    for row in await daily_chart(db, days):
        start, end = _day_bounds(row.day)
        if start < since or end > cutoff + timedelta(seconds=1):
            continue
        points.append({
            "t": (end - timedelta(seconds=1)).isoformat(), "kind": "close",
            "lots": row.bought_lots + row.sold_lots, "buy": row.buy_lot, "sell": row.sell_lot,
            "bought": row.bought_lots, "sold": row.sold_lots,
        })
    points.sort(key=lambda p: p["t"])
    return points
