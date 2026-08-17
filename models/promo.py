"""Промокоды (патч 50): создаются в админ-панели, активируются игроком текстом в чате."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Хранится в нижнем регистре (услуга регистронезависимости — на сервисном
    # слое, см. services/promo_service.py::normalize_code); сравнение при
    # активации — по этому же нормализованному значению.
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Список позиций [{"type": "gold", "amount": 500}, ...] — см.
    # services/promo_service.py::REWARD_APPLIERS для допустимых type.
    rewards: Mapped[list] = mapped_column(JSON, default=list)
    max_activations: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None — без лимита
    one_per_player: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[int] = mapped_column(BigInteger)  # vk_id администратора


class PromoActivation(Base):
    """Патч 50: НЕТ уникального ограничения (promo_code_id, character_id) —
    one_per_player настраивается ЗА КОД (некоторые коды разрешают повторные
    активации), поэтому проверка "уже использован" — на уровне сервиса
    (services/promo_service.py), не на уровне схемы."""

    __tablename__ = "promo_activations"

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
