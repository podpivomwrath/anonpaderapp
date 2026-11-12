"""Древние руины культа (2026-11-05): забег живёт в базе и переживает
перезапуск бота. Бой комнаты - в памяти (bot/handlers/raid_combat.py); если
бот перезапустился посреди боя, группа возвращается в комнату, откуда
вошла, с тем здоровьем, с каким входила (services/ruins_service.recover).
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RuinRun(Base):
    """status: active | done. outcome (для done): exited | wiped | abandoned.
    phase: walk - группа ходит; fight - идёт бой комнаты; cleared - босс
    этажа повержен, лидер решает: глубже или наверх."""

    __tablename__ = "ruin_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(8), default="active", index=True)
    outcome: Mapped[str | None] = mapped_column(String(12), nullable=True)
    leader_id: Mapped[int] = mapped_column(Integer)
    floor: Mapped[int] = mapped_column(Integer, default=1)
    #: game/ruins.generate: комнаты, вход, босс, вид мобов
    layout: Mapped[dict] = mapped_column(JSON, default=dict)
    pos: Mapped[int] = mapped_column(Integer, default=0)
    #: откуда вошли в текущую комнату - туда возвращает перезапуск посреди боя
    prev_pos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visited: Mapped[list] = mapped_column(JSON, default=list)
    cleared: Mapped[list] = mapped_column(JSON, default=list)
    phase: Mapped[str] = mapped_column(String(8), default="walk")
    #: шаг, который лидер предложил: {"dir", "to", "until", "ok": [id...]}
    pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: голосование за изгнание: {"target", "until", "yes": [...], "no": [...]}
    vote: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deepest: Mapped[int] = mapped_column(Integer, default=1)
    #: дары культа группы: [{"id", "floor": True - только на этот этаж}]
    gifts: Mapped[list] = mapped_column(JSON, default=list)
    #: дары на выбор лидеру: {"ids": [...], "until", "drop": снятый дар колодца}
    offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: прочее состояние: kills, prayer (спасённые молитвой на этаже),
    #: fight ({"kind", "after"} - бой из выбора в комнате)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_action_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuinMember(Base):
    """Участник забега. Мешок у каждого свой: {"runes": {id: n}, "trophies":
    {id: n}} - выдаётся при выходе живыми, сгорает при гибели группы и
    изгнании. active=False - вышел (изгнан или забег окончен)."""

    __tablename__ = "ruin_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("ruin_runs.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    hp: Mapped[int] = mapped_column(Integer, default=1)
    #: здоровье на входе в комнату с боем - его вернёт перезапуск посреди боя
    hp_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dead: Mapped[bool] = mapped_column(Boolean, default=False)
    consumables_used: Mapped[int] = mapped_column(Integer, default=0)
    bag: Mapped[dict] = mapped_column(JSON, default=dict)
    left_reason: Mapped[str | None] = mapped_column(String(12), nullable=True)
    #: Топ руин (2026-11-13): этаж, хозяина которого игрок убил последним в
    #: этом забеге, и когда. Изгнанный и погибшие сохраняют пройденное.
    floors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    floors_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class RuinWeek(Base):
    """Неделя топа руин подведена (понедельник по Москве). Строка ставится
    до выдачи наград: второй одновременный вызов упрётся в ключ."""

    __tablename__ = "ruin_weeks"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuinWeekResult(Base):
    """Призовое место недели топа руин: section - solo | group. Титул -
    только у строки лучшего места игрока (в двух разделах он один)."""

    __tablename__ = "ruin_week_results"
    __table_args__ = (
        UniqueConstraint("week_start", "section", "character_id", name="uq_ruin_week_result"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    section: Mapped[str] = mapped_column(String(8))
    place: Mapped[int] = mapped_column(Integer)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int] = mapped_column(Integer)
    floors: Mapped[int] = mapped_column(Integer)
    chests: Mapped[int] = mapped_column(Integer)
    title_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
