from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class CharacterStoryProgress(Base):
    """Прогресс региональной сюжетной линии (патч 18): один активный сюжетный
    квест на регион персонажа (линейно, без ветвлений).

    quest_step — id квеста из content/story/<region>.json (не БД-справочник,
    как и content/quests/class_trials.json — см. CharacterTrialProgress).
    status: "active" (квест выдан, цель ещё не достигнута) | "ready" (цель
    достигнута/бой выигран — ждёт разговора с наставником). completed=True —
    региональная линия пройдена целиком (quest_step хранит id последнего
    квеста для истории, не используется дальше).

    quest_seen (патч 21) — текущий (quest_step, status) уже был показан
    игроку обычным (не мгновенно резолвящим) визитом к наставнику. Сбрасывается
    в False при любом продвижении указателя (_advance_pointer) и при
    mark_ready — управляет пометкой [🧙 Наставник ❗] и проактивным пингом."""

    __tablename__ = "character_story_progress"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "region", name="uq_character_story_progress_character_region"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    region: Mapped[str] = mapped_column(String(16))
    act: Mapped[int] = mapped_column(default=1)
    quest_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    completed: Mapped[bool] = mapped_column(default=False)
    quest_seen: Mapped[bool] = mapped_column(default=False)
