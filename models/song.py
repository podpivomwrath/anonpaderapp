from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterSongFragment(Base):
    """Увиденный обрывок Пепельной Песни (патч 25, п.6) — 10 индексов,
    порядок = порядок content/flavor/ashen_song.json["parts"]. Полный сбор
    (все 10) открывает доп. выбор «Прочесть Пепельную Песнь» у Пепельного
    алтаря (services/song_service.py)."""

    __tablename__ = "character_song_fragments"
    __table_args__ = (
        UniqueConstraint("character_id", "fragment_index", name="uq_character_song_char_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    fragment_index: Mapped[int] = mapped_column()
