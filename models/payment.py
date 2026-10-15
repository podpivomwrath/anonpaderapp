from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class GemPayment(Base):
    """Покупка самоцветов за рубли через ЮKassa (2026-10-15).

    Строка заводится при создании платежа (pending). Самоцветы начисляются
    один раз - когда ЮKassa подтвердила оплату (credited); повторные
    уведомления ничего не меняют."""

    __tablename__ = "gem_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True)
    vk_id: Mapped[int] = mapped_column(BigInteger, index=True)
    pack_id: Mapped[str] = mapped_column(String(16))
    gems: Mapped[int] = mapped_column(Integer)
    amount_rub: Mapped[int] = mapped_column(Integer)
    yk_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    # pending | succeeded | canceled
    status: Mapped[str] = mapped_column(String(16), default="pending")
    credited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
