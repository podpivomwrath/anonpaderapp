"""Пользовательское соглашение: кто принял актуальную редакцию (2026-10-15).

Меняются документы так, что их нужно принять заново, - поднимаем
CURRENT_VERSION: у всех снова появится окно согласия.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from services import onboarding_service

CURRENT_VERSION = "2026-10-15"
SITE = "https://monolithgame.ru/legal"

DOCS = (
    ("terms", "Пользовательское соглашение", f"{SITE}/terms.html"),
    ("privacy", "Политика обработки персональных данных", f"{SITE}/privacy.html"),
    ("offer", "Публичная оферта (покупка самоцветов)", f"{SITE}/offer.html"),
)

TEXT = (
    "📜 Прежде чем продолжить\n\n"
    "Нажимая «✅ Принимаю», ты подтверждаешь, что тебе исполнилось 18 лет, и принимаешь "
    "условия игры «Monolith»:\n"
    + "\n".join(f"• {title}: {url}" for _id, title, url in DOCS)
    + "\n\nФайлы документов придут следующим сообщением. Без согласия играть нельзя."
)


def accepted(user: User | None) -> bool:
    return user is not None and user.terms_version == CURRENT_VERSION


async def user_of(db: AsyncSession, vk_id: int) -> User | None:
    return await db.scalar(select(User).where(User.vk_id == vk_id))


async def accept(db: AsyncSession, vk_id: int) -> User:
    user = await onboarding_service.get_or_create_user(db, vk_id)
    user.terms_version = CURRENT_VERSION
    user.terms_accepted_at = datetime.now(timezone.utc)
    await db.flush()
    return user
