from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterUnlockedBuff(Base):
    """Открытый бафф подкласса (патч 12): навсегда, переживает даже полный
    ресет класса (см. п.5 патча — Хранитель ничего не забывает)."""

    __tablename__ = "character_unlocked_buffs"
    __table_args__ = (
        UniqueConstraint("character_id", "buff_id", name="uq_character_unlocked_buffs_character_buff"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    buff_id: Mapped[str] = mapped_column(String(64))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterTrialProgress(Base):
    """Прогресс по классовому испытанию (патч 12): id испытания — из
    content/quests/class_trials.json, не БД-справочник (в отличие от Quest)."""

    __tablename__ = "character_trial_progress"
    __table_args__ = (
        UniqueConstraint("character_id", "trial_id", name="uq_character_trial_progress_character_trial"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    trial_id: Mapped[str] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(default=0)
    completed: Mapped[bool] = mapped_column(default=False)
