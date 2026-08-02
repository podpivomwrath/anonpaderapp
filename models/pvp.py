from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PvpBattle(Base):
    """Лог завершённого PvP-боя (патч 22) — история для профиля/аудита, не
    читается движком в рантайме (весь боевой стейт — в памяти, см.
    game/combat/duel_engine.py и bot/handlers/pvp.py).

    participant_ids/winner_ids — списки characters.id (JSON, не FK-таблица:
    участников может быть много, отдельная таблица не нужна). winner_ids
    пуст при ничьей."""

    __tablename__ = "pvp_battles"

    id: Mapped[int] = mapped_column(primary_key=True)
    battle_type: Mapped[str] = mapped_column(String(16))  # "duel" | "mass"
    participant_ids: Mapped[list] = mapped_column(JSON)
    winner_ids: Mapped[list] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
