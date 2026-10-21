"""Травничество (2026-10-21): трава на клетках мира и сумка травника."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class HerbPatch(Base):
    """Трава, выросшая на клетке. Общая для сервера: кто первый сорвал, того и
    трава. Одна клетка - одна трава. Вянет через herbal_config.LIFETIME_HOURS
    (строка остаётся, пока её не подметёт следующий рост)."""

    __tablename__ = "herb_patches"
    __table_args__ = (UniqueConstraint("x", "y", name="uq_herb_patches_cell"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    herb_id: Mapped[str] = mapped_column(String(32))
    spawned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterHerb(Base):
    """Пучки в сумке травника. Градаций у трав нет - стак по виду."""

    __tablename__ = "character_herbs"
    __table_args__ = (UniqueConstraint("character_id", "herb_id", name="uq_character_herbs_char_herb"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    herb_id: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(BigInteger, default=0)
