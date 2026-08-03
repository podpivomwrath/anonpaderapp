from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterDaily(Base):
    """Ежедневное задание, выданное персонажу на конкретный день (патч 23).

    Строки за прошедшие дни не удаляются (история) — активные для персонажа
    это ровно те, у которых date == сегодняшняя дата в московской зоне
    (services/daily_service.py сам решает, что "сегодня")."""

    __tablename__ = "character_dailies"
    __table_args__ = (
        UniqueConstraint("character_id", "quest_id", "date", name="uq_character_dailies_char_quest_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    quest_id: Mapped[str] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    date: Mapped[date] = mapped_column(Date, index=True)


class CharacterTitle(Base):
    """Разблокированный титул (патч 23, задел под будущие) — не удаляется,
    даже если персонаж переключит активный титул на другой/сбросит его."""

    __tablename__ = "character_titles"
    __table_args__ = (
        UniqueConstraint("character_id", "title_id", name="uq_character_titles_char_title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    title_id: Mapped[str] = mapped_column(String(32))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
