from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
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
    #: Имя от игрока (Турбоишак, 2026-10-19): «Турбоишак Алексей». None - ещё
    #: не назван (бот ждёт имя), "" - игрок отказался давать имя.
    nickname: Mapped[str | None] = mapped_column(String(24), nullable=True)


class TurboIshakDay(Base):
    """Турбоишак дня (2026-10-19): одна строка на московский день.

    planned - время появления выбрано, ишака ещё нет; active - бегает по
    карте (x, y - где он сейчас); caught - пойман (caught_by); gone - не
    поймали за отведённое время. Числа - game/economy/turbo_config.py."""

    __tablename__ = "turbo_ishak_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[str] = mapped_column(String(10), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="planned")
    spawn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_move_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Где стоит, а на бегу - куда бежит (2026-10-19: бежит по клеткам, как
    #: маунт, со скоростью Турбоишака). from_* и run_started_at - начало забега,
    #: run_started_at = None - стоит на (x; y).
    x: Mapped[int | None] = mapped_column(nullable=True)
    y: Mapped[int | None] = mapped_column(nullable=True)
    from_x: Mapped[int | None] = mapped_column(nullable=True)
    from_y: Mapped[int | None] = mapped_column(nullable=True)
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    caught_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    caught_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
    #: Клетки пути без стартовой, с конечной ([[x, y], ...]). None - прямая
    #: (grid.line_path); заполнен у безопасного пути (2026-10-13).
    path: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="traveling")
    # Движение по клеткам: персонаж реально стоит на клетке path[cell_index-1]
    # (0 - ещё на старте), следующий шаг - в next_cell_at, шаг длится
    # step_seconds. Путь не хранится: он однозначно считается из from/to
    # (game/world/grid.py::line_path).
    step_seconds: Mapped[float] = mapped_column(Float, default=10.0, server_default="10")
    cell_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_cell_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
