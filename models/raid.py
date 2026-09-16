"""Рейды (патч 53): лобби рейда — сбор группы у Монолита перед стартом.

Персистится ТОЛЬКО лобби (сбор может растянуться на минуты — дойти пешком
до (0;0), рестарт бота посреди этого не должен стирать прогресс готовности,
тот же резон, что у GroupInvite). Сам активный бой (этапы/HP/аггро/фазы
Хирурга) — в памяти (bot/handlers/raid_combat.py), как и групповой PvE
(bot/handlers/group_combat.py): не персистится нигде, тот же уровень риска,
что и у обычных боевых сессий — намеренное отступление от схемы БД,
предложенной в тексте патча (raid_sessions там не заводится)."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RaidLobby(Base):
    """status: waiting | started | finished. group_id NULL — соло-вход (без
    группы, патч 53 явно разрешает: "Никаких предупреждений и блокировок")."""

    __tablename__ = "raid_lobbies"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=True
    )
    raid_id: Mapped[str] = mapped_column(String(32))
    leader_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RaidLobbyMember(Base):
    """character_id unique — персонаж состоит не более чем в одном лобби
    одновременно (тот же паттерн, что GroupMember.character_id); строка
    удаляется, когда лобби покидают/распускают/стартуют (см. raid_service)."""

    __tablename__ = "raid_lobby_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    lobby_id: Mapped[int] = mapped_column(ForeignKey("raid_lobbies.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    ready: Mapped[bool] = mapped_column(Boolean, default=False)


class RaidRun(Base):
    """Durable key receipt. Active runs are interrupted/refunded at startup."""
    __tablename__ = "raid_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    leader_character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    raid_id: Mapped[str] = mapped_column(String(32))
    members: Mapped[list] = mapped_column(JSON)  # character IDs; independent of group membership
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
