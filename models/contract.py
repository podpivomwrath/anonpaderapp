"""Заказы на игроков (2026-10-16): анонимный заказ убийств цели за самоцветы.

Самоцветы списываются у заказчика при создании; за каждое убийство цели
платится price тем, кто взял заказ и участвовал в убийстве (поровну).
Через 20 часов невыполненный остаток сгорает. Числа - game/economy/contract_config.py.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Заказчик - не показывается никому, кроме него самого.
    orderer_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    kills_total: Mapped[int] = mapped_column(Integer)
    kills_left: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)          # самоцветов за одно убийство
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | done | expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ContractTaker(Base):
    """Кто взял заказ: видит цель на карте, цель не прячется от него в АФК
    и на мирных клетках, за убийство получает долю."""

    __tablename__ = "contract_takers"

    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
