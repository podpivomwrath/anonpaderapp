from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    vk_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Имя и фамилия в VK - только для поиска в админ-панели (2026-10-15).
    # Подтягивает services/vk_names_service.py фоном, в игре не показываются.
    vk_first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vk_last_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vk_names_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Принятое пользовательское соглашение (2026-10-15): версия документов и
    # когда принято. Без актуальной версии игра не пускает дальше
    # (bot/handlers/terms.py).
    terms_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    characters: Mapped[list["Character"]] = relationship(back_populates="user")


from models.character import Character  # noqa: E402  (разрешение forward-ссылки)
