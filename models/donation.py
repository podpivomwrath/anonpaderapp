"""Учёт донатов (2026-10-16, просьба владельца): кто и сколько задонатил -
для выдачи после вайпа.

Запись не ссылается на персонажа внешним ключом: учёт обязан пережить вайп
(scripts/wipe.py удаляет персонажей). vk_id и имена - снимок на момент
доната. source: yookassa - покупка самоцветов через ЮKassa (пишется сама),
manual - внесено вручную в админке.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(primary_key=True)
    vk_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    donor: Mapped[str] = mapped_column(String(160))
    character_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_rub: Mapped[int] = mapped_column(Integer)
    gems: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
