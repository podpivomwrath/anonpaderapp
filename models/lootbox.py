from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterLootbox(Base):
    """Лог открытого Пепельного ларца (патч 24) — история для мини-аппа
    (последние открытия + счётчик по градациям). Открывается СРАЗУ при
    выдаче (см. services/lootbox_service.py) — неоткрытых ларцов не бывает,
    эта таблица только фиксирует уже случившийся результат."""

    __tablename__ = "character_lootboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    grade: Mapped[str] = mapped_column(String(16))
    reward_summary: Mapped[str] = mapped_column(String(256))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
