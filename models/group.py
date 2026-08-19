"""Группы (патч 51, ч.2): до 5 игроков, лидер приглашает/исключает, лидерство
переходит следующему по порядку вступления при выходе лидера."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    leader_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupMember(Base):
    """joined_at — порядок вступления важен: при выходе лидера лидерство
    переходит СЛЕДУЮЩЕМУ по этому полю (не по id, хотя на практике совпадает —
    строки не переиспользуются)."""

    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), unique=True, index=True
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GroupInvite(Base):
    """status: pending | accepted | declined | expired. Действует 1 минуту
    (services/group_service.py::INVITE_TTL_SECONDS) — истечение проверяется
    по expires_at при каждом обращении, отдельного воркера нет (тот же
    паттерн, что и у промокодов патча 50).

    group_id NULLABLE: группа создаётся автоматически ПРИ ПРИНЯТИИ первого
    приглашения (не при отправке) — пока лидер ещё не привёл никого, у него
    самого группы нет, group_id=None, id будущего лидера — from_character_id."""

    __tablename__ = "group_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True, nullable=True
    )
    from_character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    to_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")
