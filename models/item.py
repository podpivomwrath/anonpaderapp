from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Item(Base):
    """Экземпляр предмета.

    Прогрессия (п.9 дизайна): 1-59 — тиры по цвету с шансом дропа;
    60+ — рейд-сеты каждые 10 уровней (крафт или 100%-дроп, без рандома).
    Внутри окна предмет прокачивается заточкой (до +20) и пробуждением.
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    slot: Mapped[str] = mapped_column(String(32))
    base_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    # Ключ из balance_config.TIER_MULTIPLIERS: grey|white|green|blue|epic|legendary
    tier: Mapped[str] = mapped_column(String(20), default="grey")
    enchant_level: Mapped[int] = mapped_column(default=0)
    awakened: Mapped[bool] = mapped_column(Boolean, default=False)
    # Самоцвет — отдельный прокачиваемый предмет, вставляется после пробуждения
    socketed_gem_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id"), nullable=True
    )


class ItemUpgradeHistory(Base):
    """История попыток заточки/пробуждения (аудит + аналитика баланса).

    item_id обнуляется при уничтожении предмета (SET NULL) — запись остаётся.
    """

    __tablename__ = "item_upgrade_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(16))  # enchant | awaken
    success: Mapped[bool] = mapped_column(Boolean)
    level_before: Mapped[int] = mapped_column()
    level_after: Mapped[int] = mapped_column()
    # Пробуждение может уничтожить предмет (30%)
    item_destroyed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Inventory(Base):
    """Связка персонаж ↔ предмет.

    Композитный PK достаточен для v1: предмет — уникальный экземпляр.
    Стаки/количество появятся позже отдельной миграцией.
    """

    __tablename__ = "inventory"

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    equipped: Mapped[bool] = mapped_column(Boolean, default=False)
