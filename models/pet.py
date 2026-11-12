from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterPet(Base):
    """Питомец, которым владеет персонаж (2026-11-12). Каждый вид - один раз:
    повторно не выдаётся. Какой в слоте - character.pet_id
    (services/pet_service.py)."""

    __tablename__ = "character_pets"
    __table_args__ = (UniqueConstraint("character_id", "pet_id", name="uq_character_pets_char_pet"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    pet_id: Mapped[str] = mapped_column(String(24))
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AshDragon(Base):
    """Пепельный дракон (2026-11-12): одна строка на весь мир (id=1).

    code - что пишет Странная руна; кто первым введёт его у Монолита с руной
    в слоте, тот будит дракона. awakened_at ставится условным UPDATE (только
    если пусто) - двое одновременно его не получат. Где дракон сейчас -
    character_mounts (его можно передать), здесь только кто разбудил."""

    __tablename__ = "ash_dragon"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32))
    awakened_by: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    awakened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
