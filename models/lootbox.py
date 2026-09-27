from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterLootbox(Base):
    """Пепельный ларец (патч 24) - предмет в сумке.

    С патча 106 ларец не открывается сам при выдаче: он ложится в сумку
    закрытым (status='closed'), и игрок открывает его в мини-аппе рулеткой.
    Градация и награда появляются только в момент открытия - их и
    разыгрывает рулетка. Открытые строки - история для мини-аппа.
    """

    __tablename__ = "character_lootboxes"
    __table_args__ = (Index("ix_character_lootboxes_char_status", "character_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    #: closed - лежит в сумке; opened - открыт
    status: Mapped[str] = mapped_column(String(8), default="opened")
    #: день стрика ежедневок, за который выдан: от него шансы градаций
    streak: Mapped[int | None] = mapped_column(nullable=True)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reward_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
