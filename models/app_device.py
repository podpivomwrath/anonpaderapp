"""Приложение «Монолит» для Windows и Android (2026-11-15, владелец).

Вход без VK ID: игрок в мини-аппе жмёт «Авторизовать приложение», получает
одноразовый код и вводит его в приложении. Приложение получает свой ключ и
дальше ходит в тот же API, что и мини-апп (services/app_link_service.py).

В базе хранится только SHA-256 кода и ключа: утечка базы не даёт войти.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AppDevice(Base):
    """Подключённое устройство. Отключённое (revoked_at) больше не входит."""

    __tablename__ = "app_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    #: как устройство назвало себя («ПК», модель телефона) - для списка в мини-аппе
    name: Mapped[str] = mapped_column(String(48))
    platform: Mapped[str] = mapped_column(String(16))  # windows | android
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppPairCode(Base):
    """Одноразовый код привязки, живёт PAIR_CODE_SECONDS. У игрока - один:
    новый код заменяет старый."""

    __tablename__ = "app_pair_codes"

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
