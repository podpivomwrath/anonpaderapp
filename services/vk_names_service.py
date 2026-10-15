"""Имя и фамилия игроков из VK - для поиска в админ-панели (2026-10-15).

В игре не показываются нигде: только поиск и карточка игрока у админа.
Обновляем фоном пачками (users.get принимает до 1000 id за запрос), раз в
REFRESH_HOURS на игрока - люди меняют имя редко.
"""

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User

REFRESH_HOURS = 24
RETRY_EMPTY_HOURS = 1
BATCH = 500


async def refresh(db: AsyncSession, api, now: datetime | None = None) -> int:
    """Подтянуть имена тем, у кого их нет или они старше REFRESH_HOURS.
    Возвращает, скольким обновили."""
    now = now or datetime.now(timezone.utc)
    users = (await db.scalars(
        select(User).where(or_(
            User.vk_names_at.is_(None),
            User.vk_names_at < now - timedelta(hours=REFRESH_HOURS),
            # Имя не записалось (сбой ответа) - повтор через час, а не через сутки.
            and_(User.vk_first_name.is_(None), User.vk_names_at < now - timedelta(hours=RETRY_EMPTY_HOURS)),
        ))
        .order_by(User.vk_names_at.nulls_first()).limit(BATCH)
    )).all()
    if not users:
        return 0
    try:
        found = await api.users.get(user_ids=[u.vk_id for u in users])
    except Exception as exc:  # noqa: BLE001 - фоновая задача, повторим в следующий раз
        logger.warning("Имена VK не подтянулись: {}", exc)
        return 0
    by_id = {p.id: p for p in found or []}
    for u in users:
        person = by_id.get(u.vk_id)
        if person is not None:
            u.vk_first_name = (person.first_name or "")[:64] or None
            u.vk_last_name = (person.last_name or "")[:64] or None
        u.vk_names_at = now
    await db.flush()
    return len(users)


def full_name(user: User | None) -> str | None:
    if user is None:
        return None
    name = " ".join(p for p in (user.vk_first_name, user.vk_last_name) if p)
    return name or None
