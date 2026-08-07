"""Админка (патч 27): журнал действий, репорты багов, лог смертей."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AdminAction(Base):
    """Журнал действий администратора над игроками — кто/что/над кем/когда.

    target_character_id намеренно ondelete=SET NULL (не CASCADE): запись в
    журнале должна пережить удаление персонажа, см. тот же паттерн для
    item_upgrade_history в scripts/wipe.py.
    """

    __tablename__ = "admin_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_vk_id: Mapped[int] = mapped_column(BigInteger)
    action_type: Mapped[str] = mapped_column(String(32))
    target_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BugReport(Base):
    """Репорт бага от игрока (/баг) — текст + снимок состояния на момент отправки."""

    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(String(2000))
    snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new|in_progress|closed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterDeath(Base):
    """Лог смертей (патч 27) — для статистики «смертей за сутки, топ зон по смертям»."""

    __tablename__ = "character_deaths"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pos_x: Mapped[int | None] = mapped_column(nullable=True)
    pos_y: Mapped[int | None] = mapped_column(nullable=True)
    cause: Mapped[str] = mapped_column(String(8))  # "pve"|"pvp"
    died_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
