"""Разломы (2026-10): случайные данжи на карте.

Разлом живёт в базе: место, тип, срок и кто сейчас его держит. Бой внутри -
в памяти (bot/handlers/raid_combat.py), как у рейдов; после перезапуска
бота занятый разлом освобождается (services/rift_service.recover).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Rift(Base):
    """status: active | cleared | expired - живой, пройден, исчез.
    state (для active): free | waiting | running - свободен, группа ждёт
    60 секунд у входа, группа внутри."""

    __tablename__ = "rifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    ring: Mapped[int] = mapped_column()
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    state: Mapped[str] = mapped_column(String(16), default="free")
    #: кто держит разлом (ожидание или бой): id персонажей, лидер - первым
    members: Mapped[list] = mapped_column(JSON, default=list)
    group_id: Mapped[int | None] = mapped_column(nullable=True)
    wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: уровень противников захода - по старшему в группе, в пределах разлома
    level: Mapped[int | None] = mapped_column(nullable=True)
    spawned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiftMeter(Base):
    """Счётчик появления: одна строка на мир (id=1), как у мировых боссов."""

    __tablename__ = "rift_meter"

    id: Mapped[int] = mapped_column(primary_key=True)
    explorations: Mapped[int] = mapped_column(default=0)
