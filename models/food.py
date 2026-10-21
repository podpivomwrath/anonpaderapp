"""Кулинария (2026-10-21): готовые блюда в инвентаре."""

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterFood(Base):
    """Порции блюда. Стак по (блюдо + градация рыбы): от градации зависит сила."""

    __tablename__ = "character_food"
    __table_args__ = (UniqueConstraint("character_id", "dish_id", "grade", name="uq_character_food"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    dish_id: Mapped[str] = mapped_column(String(32))
    grade: Mapped[str] = mapped_column(String(16))
    count: Mapped[int] = mapped_column(BigInteger, default=0)
