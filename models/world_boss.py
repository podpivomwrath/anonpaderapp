"""Мировые боссы (патч 104): состояние мира, общее для всех игроков."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class WorldBoss(Base):
    """Один появившийся босс - живой или уже закончившийся.

    Здоровье общее: каждый заход любого игрока снимает с hp. Живой босс в
    мире один (status='active'); закончившиеся остаются строками, по ним
    видно, как часто боссов убивают и сколько они стоят на карте.
    """

    __tablename__ = "world_bosses"
    __table_args__ = (Index("ix_world_bosses_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: id облика из content/world_bosses.json
    boss_id: Mapped[str] = mapped_column(String(48))
    ring: Mapped[int] = mapped_column()
    level: Mapped[int] = mapped_column()
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    max_hp: Mapped[int] = mapped_column(BigInteger)
    hp: Mapped[int] = mapped_column(BigInteger)
    #: active | killed | escaped
    status: Mapped[str] = mapped_column(String(16), default="active")
    spawned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorldBossContribution(Base):
    """Вклад одного игрока в одного босса: урон и время последнего захода."""

    __tablename__ = "world_boss_contributions"
    __table_args__ = (
        UniqueConstraint("world_boss_id", "character_id", name="uq_world_boss_contribution"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    world_boss_id: Mapped[int] = mapped_column(
        ForeignKey("world_bosses.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    damage: Mapped[int] = mapped_column(BigInteger, default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorldBossMeter(Base):
    """Счётчик пробуждения: одна строка на весь мир (id=1).

    Каждое завершённое исследование добавляет единицу; заполненный счётчик
    выпускает босса. Строка заводится лениво, как жилы рудников.
    """

    __tablename__ = "world_boss_meter"

    id: Mapped[int] = mapped_column(primary_key=True)
    explorations: Mapped[int] = mapped_column(default=0)
    last_spawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
