"""Торговля: повозка игрока, давление рынка по городам, караваны на карте.

Числа - game/economy/trade_config.py, логика - services/trade_service.py.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterCart(Base):
    """Повозка (одна на персонажа) и ремесло торговли.

    Повозка стоит там, где её оставили (cart_x/cart_y): грузить и продавать
    можно, только когда игрок рядом с ней в городе или у каравана. В пути
    она едет вместе с игроком (mount_travels с mount_id = CART_MOUNT_ID).
    cargo - {good_id: ящиков}; paid - {good_id: золота уплачено} для расчёта
    прибыли в отчёте о продаже."""

    __tablename__ = "character_carts"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    cart_x: Mapped[int] = mapped_column(Integer)
    cart_y: Mapped[int] = mapped_column(Integer)
    horses: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[int] = mapped_column(Integer, default=1)
    plating: Mapped[int] = mapped_column(Integer, default=1)
    guard: Mapped[int] = mapped_column(Integer, default=1)
    #: Сколько ещё нападений выдержит обшивка до поломки.
    durability: Mapped[int] = mapped_column(Integer, default=2)
    cargo: Mapped[dict] = mapped_column(JSON, default=dict)
    paid: Mapped[dict] = mapped_column(JSON, default=dict)
    trade_level: Mapped[int] = mapped_column(Integer, default=1)
    trade_xp: Mapped[int] = mapped_column(Integer, default=0)
    profit_total: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeMarket(Base):
    """Давление на цену товара в городе: + после продаж туда (цена ниже),
    + после покупок у производителя (цена выше). Спадает со временем."""

    __tablename__ = "trade_markets"

    city: Mapped[str] = mapped_column(String(16), primary_key=True)
    good_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    pressure: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TradeCaravan(Base):
    """Караван на карте: стоит на клетке до expires_at. buys/sells -
    {good_id: ящиков осталось}; цены - от базы с множителями каравана."""

    __tablename__ = "trade_caravans"

    id: Mapped[int] = mapped_column(primary_key=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    buys: Mapped[dict] = mapped_column(JSON, default=dict)
    sells: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
