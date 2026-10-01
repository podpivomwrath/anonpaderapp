from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    farm_currency: Mapped[int] = mapped_column(BigInteger, default=0)   # золото
    donate_currency: Mapped[int] = mapped_column(BigInteger, default=0)


class ExchangeOrder(Base):
    """Исполненная сделка на бирже (игра — дилер, не P2P ордербук)."""

    __tablename__ = "exchange_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    # Значения из models.enums.OrderDirection: buy | sell (донат-валюты)
    direction: Mapped[str] = mapped_column(String(4))
    amount: Mapped[int] = mapped_column(BigInteger)          # донат-валюта
    gold_amount: Mapped[int] = mapped_column(BigInteger, default=0)  # уплачено/получено золота
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExchangeState(Base):
    """Состояние биржи: одна строка (id=1) - чистый объём самоцветов,
    проданных игрокам (купили минус продали). От него считается курс.

    В базе, а не в Redis: сделка и сдвиг курса обязаны жить в одной
    транзакции под одной блокировкой - иначе два одновременных лота
    прошли бы по одной цене.
    """

    __tablename__ = "exchange_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    net_sold: Mapped[int] = mapped_column(BigInteger, default=0)


class ExchangeDaily(Base):
    """Курс на закрытие дня (МСК) - точка графика биржи. Пишется раз в сутки
    сразу после полуночи (задача exchange_snapshot в main.py)."""

    __tablename__ = "exchange_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    buy_lot: Mapped[int] = mapped_column(BigInteger)
    sell_lot: Mapped[int] = mapped_column(BigInteger)
    bought_lots: Mapped[int] = mapped_column(default=0)
    sold_lots: Mapped[int] = mapped_column(default=0)
