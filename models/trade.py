"""Торговля: фирма игрока, её повозки, журнал рейсов, давление рынка,
процветание городов и вклад торговцев.

Числа - game/economy/trade_config.py и faction_config.py, логика -
services/trade_service.py и services/faction_service.py.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TradeFirm(Base):
    """Торговая фирма (одна на персонажа) и ремесло торговли.

    name - название, пока пусто (перенос со старых повозок), фирма закрыта:
    сначала назвать. name_key - название в нижнем регистре для уникальности."""

    __tablename__ = "trade_firms"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str | None] = mapped_column(String(24), nullable=True)
    name_key: Mapped[str | None] = mapped_column(String(24), nullable=True, unique=True)
    trade_level: Mapped[int] = mapped_column(Integer, default=1)
    trade_xp: Mapped[int] = mapped_column(Integer, default=0)
    profit_total: Mapped[int] = mapped_column(BigInteger, default=0)
    notify_arrival: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_orders: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeCart(Base):
    """Повозка фирмы. Стоит в городе city (status idle) или едет из city в
    to_city (status traveling) до arrives_at. cargo - {good_id: ящиков},
    paid - {good_id: золота уплачено}; ambushes - сколько раз нападут в пути
    (разыграно при отправке, применяется по прибытии)."""

    __tablename__ = "trade_carts"
    __table_args__ = (UniqueConstraint("character_id", "slot", name="uq_trade_carts_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(12), default="idle")
    to_city: Mapped[str | None] = mapped_column(String(16), nullable=True)
    route: Mapped[str | None] = mapped_column(String(8), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrives_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ambushes: Mapped[int] = mapped_column(Integer, default=0)
    horses: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[int] = mapped_column(Integer, default=1)
    plating: Mapped[int] = mapped_column(Integer, default=1)
    guard: Mapped[int] = mapped_column(Integer, default=1)
    #: Сколько ещё нападений выдержит обшивка до поломки.
    durability: Mapped[int] = mapped_column(Integer, default=2)
    cargo: Mapped[dict] = mapped_column(JSON, default=dict)
    paid: Mapped[dict] = mapped_column(JSON, default=dict)


class TradeTrip(Base):
    """Журнал рейсов: что везли, сколько выручили, что случилось в пути."""

    __tablename__ = "trade_trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    from_city: Mapped[str] = mapped_column(String(16))
    to_city: Mapped[str] = mapped_column(String(16))
    route: Mapped[str] = mapped_column(String(8))
    crates: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[int] = mapped_column(Integer, default=0)
    profit: Mapped[int] = mapped_column(Integer, default=0)
    ambushes: Mapped[int] = mapped_column(Integer, default=0)
    lost: Mapped[dict] = mapped_column(JSON, default=dict)
    arrived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TradeMarket(Base):
    """Давление на цену товара в городе: + после продаж туда (цена ниже),
    + после покупок у производителя (цена выше). Спадает со временем."""

    __tablename__ = "trade_markets"

    city: Mapped[str] = mapped_column(String(16), primary_key=True)
    good_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pressure: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FactionState(Base):
    """Процветание города: очки на момент updated_at (падение - лениво)."""

    __tablename__ = "faction_states"

    city: Mapped[str] = mapped_column(String(16), primary_key=True)
    points: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TradeContribution(Base):
    """Вклад торговца в процветание родного города за сутки (по Москве):
    points - засчитано с учётом дневного потолка, raw - без потолка (для
    недельного рейтинга)."""

    __tablename__ = "trade_contributions"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    city: Mapped[str] = mapped_column(String(16), index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    raw: Mapped[int] = mapped_column(Integer, default=0)
