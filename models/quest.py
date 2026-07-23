from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class Quest(Base):
    """Определение квеста (справочные данные, сеются из content/quests.json).

    Вайп персонажей эту таблицу не трогает — квесты переживают вайп.
    """

    __tablename__ = "quests"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    # models.enums.Region: ridge|woods|docks|scorched
    region: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(64))
    progress_label: Mapped[str] = mapped_column(String(64))
    target_count: Mapped[int] = mapped_column()
    xp_reward: Mapped[int] = mapped_column()
    gold_reward: Mapped[int] = mapped_column()


class CharacterQuest(Base):
    __tablename__ = "character_quests"
    __table_args__ = (
        UniqueConstraint("character_id", "quest_id", name="uq_character_quests_character_quest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    quest_id: Mapped[int] = mapped_column(ForeignKey("quests.id"))
    progress: Mapped[int] = mapped_column(default=0)
    # models.enums.QuestStatus: active|ready|completed
    status: Mapped[str] = mapped_column(String(16), default="active")

    quest: Mapped["Quest"] = relationship()
