"""Ремесленные инструменты (2026-10-23): по строке на инструмент персонажа.

Инструмент один на слот и сразу «надет»: снимать ремесленный инструмент
незачем, а лишний экземпляр только засорял бы сумку. Новая ковка тира выше
заменяет старый. Не ломается и не передаётся (решение владельца).

tier - тир (1-5) у кованых и травяных; у добычи (альманах, лампа) 1.
count - заряды пряностей или число склянок; у остальных 0.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterCraftGear(Base):
    __tablename__ = "character_craft_gear"
    __table_args__ = (UniqueConstraint("character_id", "tool_id", name="uq_craft_gear_char_tool"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    tool_id: Mapped[str] = mapped_column(String(16))
    tier: Mapped[int] = mapped_column(default=1)
    count: Mapped[int] = mapped_column(BigInteger, default=0)
    #: Альманах (2026-10-29): когда кончились срабатывания и пошла зарядка;
    #: used - сколько срабатываний потрачено, count - найденные страницы.
    cycle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used: Mapped[int] = mapped_column(default=0, server_default="0")
    #: Альманах: подсказывать только траву этого тира; None - любую.
    herb_tier: Mapped[int | None] = mapped_column(nullable=True)
