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
