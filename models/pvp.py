from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
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
    #: Кто дрался (2026-10-21): [{"id", "level", "sub"}] на момент боя - для
    #: честной статистики подклассов на равных уровнях (pvp_service.subclass_winrates).
    participants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PvpSeasonResult(Base):
    """Итог сезона PvP (2026-10-30, владелец): пятёрка лучших по PTS с
    допуском по числу боёв. Уникальность места в сезоне - защита от двойной
    выдачи наград, если сезон закрывают два вызова сразу."""

    __tablename__ = "pvp_season_results"
    __table_args__ = (
        UniqueConstraint("season", "place", name="uq_pvp_season_place"),
        UniqueConstraint("season", "character_id", name="uq_pvp_season_character"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[str] = mapped_column(String(7), index=True)
    place: Mapped[int] = mapped_column(Integer)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    pts: Mapped[int] = mapped_column(Integer)
    fights: Mapped[int] = mapped_column(Integer)
    title_id: Mapped[str] = mapped_column(String(32))
    gems: Mapped[int] = mapped_column(Integer)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
