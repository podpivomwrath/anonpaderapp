"""Руны (2026-10-31): сумка, мастерство и слоты. Каталог - game/economy/runes_config.py."""

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterRune(Base):
    """Руны в сумке - стопкой по виду. Вставленная в слот руна отсюда уходит."""

    __tablename__ = "character_runes"
    __table_args__ = (UniqueConstraint("character_id", "rune_id", name="uq_character_rune"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    rune_id: Mapped[str] = mapped_column(String(24))
    count: Mapped[int] = mapped_column(BigInteger, default=0)


class CharacterRuneMastery(Base):
    """Личное мастерство по виду руны: сколько копий впитано. Не теряется,
    если руну снять или продать."""

    __tablename__ = "character_rune_mastery"
    __table_args__ = (UniqueConstraint("character_id", "rune_id", name="uq_character_rune_mastery"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    rune_id: Mapped[str] = mapped_column(String(24))
    absorbed: Mapped[int] = mapped_column(BigInteger, default=0)


class CharacterRuneSlot(Base):
    """Вставленная руна. slot: руны героя - номер ("0".."11"), экипировки -
    "место:номер" ("weapon:0"), навыков - "id навыка:номер"."""

    __tablename__ = "character_rune_slots"
    __table_args__ = (UniqueConstraint("character_id", "kind", "slot", name="uq_character_rune_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    slot: Mapped[str] = mapped_column(String(48))
    rune_id: Mapped[str] = mapped_column(String(24))
