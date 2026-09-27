"""Долгоживущее состояние событий исследования (патч 110).

Сама сцена события живёт в памяти процесса, как и раньше. А след на карте
и эффект на несколько боёв тянутся минутами и десятками минут - им нужно
пережить рестарт бота, поэтому они в БД.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class EventTrail(Base):
    """Активный след: один на персонажа, новый заменяет старый."""

    __tablename__ = "event_trails"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    #: Номер отрезка у ложного следа (1 - первый).
    stage: Mapped[int] = mapped_column(default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterEventEffect(Base):
    """Эффект события на N ближайших одиночных боёв с мобами."""

    __tablename__ = "character_event_effects"
    __table_args__ = (
        UniqueConstraint("character_id", "effect_id", name="uq_character_event_effects"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    effect_id: Mapped[str] = mapped_column(String(32))
    fights_left: Mapped[int] = mapped_column()
