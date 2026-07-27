from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterConsumable(Base):
    """Счётчик зелий/эликсиров по виду (патч 16): стакающийся ресурс, как
    CharacterTrophy — "🧪 Малое исцеление ×3", не 3 отдельные записи."""

    __tablename__ = "character_consumables"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "elixir_id", name="uq_character_consumables_character_elixir"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    elixir_id: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(default=0)
