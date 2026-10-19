"""Журнал передач между игроками."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TransferLog(Base):
    """Одна передача: кто, кому, что и сколько.

    Передача необратима, и если всплывёт дюп или жалоба «у меня пропало»,
    разбираться можно только по журналу. Удаление персонажа журнал не
    стирает - ссылка обнуляется, запись остаётся.
    """

    __tablename__ = "transfer_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    to_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: gold | gems | elixir | ore | item
    kind: Mapped[str] = mapped_column(String(16))
    #: id эликсира, «руда:градация», id предмета; пусто у валют
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: что именно - как видел игрок (имя предмета меняется при перековке)
    label: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class CourierDelivery(Base):
    """Посылка у курьера (2026-10-19, services/courier_service.py).

    Вещь уже списана у отправителя (take) и лежит здесь, пока курьер не
    отдаст её получателю (give). Курьер бежит по клеткам: phase="pickup" -
    из родного города отправителя к нему, "deliver" - к получателю. Цель -
    там, где персонаж стоит СЕЙЧАС: ушёл с клетки - курьер поворачивает.
    status: active | delivered | returned.
    """

    __tablename__ = "courier_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipient_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str] = mapped_column(String(160))
    amount: Mapped[int] = mapped_column(BigInteger)
    #: Видно ли получателю ник отправителя (то же правило, что у передачи).
    reveal_sender: Mapped[bool] = mapped_column(default=False)
    phase: Mapped[str] = mapped_column(String(10), default="pickup")
    status: Mapped[str] = mapped_column(String(10), default="active", index=True)
    #: Где курьер сейчас и когда сделал последний шаг.
    x: Mapped[int] = mapped_column()
    y: Mapped[int] = mapped_column()
    last_step_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Ждёт получателя на его клетке (бой, рейд) - сообщение отправлено один раз.
    waiting: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
