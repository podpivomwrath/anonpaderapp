"""Долгое путешествие (AFK) персонажа - одно на персонажа, своего города.

Строка появляется при покупке снаряжения и живёт дальше: уровни частей
копятся. status="away" - в пути; next_event_at - когда следующее событие;
ends_at - когда кончится запас хода. Числа - game/economy/voyage_config.py.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterVoyage(Base):
    __tablename__ = "character_voyages"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    region: Mapped[str] = mapped_column(String(16))
    endurance: Mapped[int] = mapped_column(Integer, default=1)
    haul: Mapped[int] = mapped_column(Integer, default=1)
    guide: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(8), default="home", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hours_done: Mapped[int] = mapped_column(Integer, default=0)
    trip_xp: Mapped[int] = mapped_column(BigInteger, default=0)
    trip_gold: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Найдено за поход: {id реликвии или "chest": штук} - для итога.
    trip_items: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Последнее событие («тир:номер») - чтобы одно и то же не выпало подряд.
    last_event: Mapped[str | None] = mapped_column(String(24), nullable=True)
    voyages_total: Mapped[int] = mapped_column(Integer, default=0)
