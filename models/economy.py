from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
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


class PvpStakeTransfer(Base):
    """Перевод ставки по итогам PvP: победитель забирает долю farm-валюты
    проигравшего (процент — в balance_config). При ничьей переводов нет."""

    __tablename__ = "pvp_stake_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("combat_sessions.id", ondelete="CASCADE"), index=True
    )
    loser_character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    winner_character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"))
    amount: Mapped[int] = mapped_column(BigInteger)  # farm-валюта
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
