"""Рынок (2026-10-23): заявки на товары, витрина снаряжения, сделки и
«ящик» купленного. Логика - services/market_service.py.

Товар - строка-ключ (game/economy/market_config.py): «ore:salt_quartz:rare»,
«herb:bitter_wormwood», «food:wormwood_soup:big», «craft:bait»,
«chest:ashen:7», а у витрины - «item:<id предмета>».
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class MarketOrder(Base):
    """Заявка. sell - товар уже списан у продавца (лежит «на рынке»), buy -
    золото покупателя уже списано: price * qty_left. Лот витрины - sell
    c good «item:<id>» и qty 1, сам предмет снят из инвентаря."""

    __tablename__ = "market_orders"
    __table_args__ = (Index("ix_market_orders_book", "good", "side", "status", "price"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    side: Mapped[str] = mapped_column(String(4))           # sell | buy
    good: Mapped[str] = mapped_column(String(64))
    price: Mapped[int] = mapped_column(BigInteger)          # золото за штуку
    qty_total: Mapped[int] = mapped_column()
    qty_left: Mapped[int] = mapped_column()
    #: open | filled | cancelled | expired
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MarketTrade(Base):
    """Сделка - для истории цен и «моих сделок»."""

    __tablename__ = "market_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    good: Mapped[str] = mapped_column(String(64), index=True)
    price: Mapped[int] = mapped_column(BigInteger)
    qty: Mapped[int] = mapped_column()
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), index=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MarketInbox(Base):
    """Купленное ждёт покупателя: забрать можно в любом городе."""

    __tablename__ = "market_inbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    good: Mapped[str] = mapped_column(String(64))
    qty: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
