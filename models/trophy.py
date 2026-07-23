from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterTrophy(Base):
    """Счётчик трофеев по градации (патч 9): стакающийся ресурс, не отдельные
    предметы — "🟣 Кровяной осколок ×7", не 7 отдельных записей."""

    __tablename__ = "character_trophies"
    __table_args__ = (
        UniqueConstraint("character_id", "trophy_id", name="uq_character_trophies_character_trophy"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    trophy_id: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(BigInteger, default=0)
