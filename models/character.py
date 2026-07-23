from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    # Значения из models.enums.BaseClass; хранится как VARCHAR (см. комментарий в enums.py)
    base_class: Mapped[str] = mapped_column(String(20))
    # id подкласса из game.classes.REGISTRY (guardian, blood_knight, ...)
    subclass: Mapped[str | None] = mapped_column(String(32), nullable=True)
    level: Mapped[int] = mapped_column(default=1)
    experience: Mapped[int] = mapped_column(BigInteger, default=0)
    # Текущее HP между боями (NULL = полное). Восстанавливается отдыхом/респавном.
    current_hp: Mapped[int | None] = mapped_column(nullable=True)
    # Момент, до которого персонаж мёртв (NULL — жив)
    respawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Стартовый регион (models.enums.Region: ridge|woods|docks|scorched).
    # Выбор ПОСТОЯННЫЙ: смена региона — будущая дорогая платная операция.
    # Регион = нарратив/квесты, PvP от него не зависит.
    region: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Шаг FSM создания персонажа; NULL = создание завершено
    creation_state: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Позиция на карте (сетка -50..50); NULL до завершения онбординга
    pos_x: Mapped[int | None] = mapped_column(nullable=True)
    pos_y: Mapped[int | None] = mapped_column(nullable=True)
    # Перемещение по клетке занимает время (world_config.CELL_TRAVEL_SECONDS);
    # travel_arrives_at = NULL — персонаж не в пути
    travel_target_x: Mapped[int | None] = mapped_column(nullable=True)
    travel_target_y: Mapped[int | None] = mapped_column(nullable=True)
    travel_arrives_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="characters")
    stats: Mapped["CharacterStats"] = relationship(
        back_populates="character", uselist=False, cascade="all, delete-orphan"
    )
    buff_presets: Mapped[list["CharacterBuffPreset"]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )


class CharacterStats(Base):
    __tablename__ = "character_stats"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    # Атрибуты названы полными словами, чтобы не конфликтовать с builtin'ами
    # str/int; имена колонок в БД — короткие, как в дизайн-документе.
    strength: Mapped[int] = mapped_column("str", default=15)
    agility: Mapped[int] = mapped_column("agi", default=15)
    intellect: Mapped[int] = mapped_column("int", default=15)
    vitality: Mapped[int] = mapped_column("vit", default=15)
    will: Mapped[int] = mapped_column("wil", default=15)
    unspent_points: Mapped[int] = mapped_column(default=0)

    character: Mapped["Character"] = relationship(back_populates="stats")


class CharacterBuffPreset(Base):
    __tablename__ = "character_buff_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    buff_ids: Mapped[list] = mapped_column(JSON, default=list)  # JSON-массив id баффов
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    character: Mapped["Character"] = relationship(back_populates="buff_presets")


# Никнейм уникален без учёта регистра ("Vasya" и "vasya" — конфликт)
Index("uq_characters_name_lower", func.lower(Character.name), unique=True)

from models.user import User  # noqa: E402
