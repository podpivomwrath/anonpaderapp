from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CombatSession(Base):
    __tablename__ = "combat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Значения из models.enums.CombatType: pve | pvp_group | duel
    type: Mapped[str] = mapped_column(String(16))
    # Значения из models.enums.CombatStatus: pending | active | finished
    status: Mapped[str] = mapped_column(String(16), default="pending")
    tick_number: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Победившая сторона (0/1); NULL — бой идёт или ничья
    winner_side: Mapped[int | None] = mapped_column(nullable=True)


class CombatParticipant(Base):
    """Участник боя: либо персонаж (character_id), либо моб (mob_id из content/).

    Суррогатный id добавлен, т.к. естественный ключ невозможен при nullable-паре
    character_id/mob_id.
    """

    __tablename__ = "combat_participants"
    __table_args__ = (
        CheckConstraint(
            "(character_id IS NOT NULL) OR (mob_id IS NOT NULL)",
            name="character_or_mob",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("combat_sessions.id", ondelete="CASCADE"), index=True
    )
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    mob_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    side: Mapped[int] = mapped_column(default=0)  # 0/1 — команда участника
    current_hp: Mapped[int] = mapped_column()
    # Объявленное действие на текущий тик; сбрасывается (NULL) после каждого резолва
    declared_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
