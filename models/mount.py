from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterMount(Base):
    """Маунт, которым владеет персонаж (патч 25, п.7) — задел на будущее:
    пока единственный источник — награда за Пепельную Песнь (services/
    song_service.py), но структура рассчитана на будущие источники."""

    __tablename__ = "character_mounts"
    __table_args__ = (
        UniqueConstraint("character_id", "mount_id", name="uq_character_mounts_char_mount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    mount_id: Mapped[str] = mapped_column(String(32))
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MountTravel(Base):
    """Активная (или последняя) поездка на маунте (патч 25, п.7). Хранится в
    БД, а не только в памяти — чтобы пережить перезапуск бота (батч-сканер
    services/mount_service.py::scan, по образцу bot/handlers/respawn.py).

    status: "traveling" | "ambushed" | "completed" | "cancelled".
    ambush_at — момент в пути, выбранный случайно СТРОГО между стартом и
    прибытием (не в начале и не в конце, патч 25 п.7); ambush_done — уже
    сработала ли (защита от повторного нападения при батч-скане)."""

    __tablename__ = "mount_travels"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    mount_id: Mapped[str] = mapped_column(String(32))
    from_x: Mapped[int] = mapped_column()
    from_y: Mapped[int] = mapped_column()
    to_x: Mapped[int] = mapped_column()
    to_y: Mapped[int] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # None — на эту поездку нападение не выпало (шанс не сыгран при старте)
    ambush_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ambush_done: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="traveling")
