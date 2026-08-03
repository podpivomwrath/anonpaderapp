"""Титулы, разблокированные персонажем (патч 23, п.8 — задел; патч 25, п.6:
первое реальное использование помимо стрика ежедневок). Общий разблокиратор
для разных источников наград — не привязан к конкретной механике."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, CharacterTitle

TITLE_NAMES = {
    "relentless": "Неотступный",  # патч 24: 365 дней стрика ежедневок
    "chronicler": "Летописец",  # патч 25: полный сбор Пепельной Песни
}


async def unlock(db: AsyncSession, character: Character, title_id: str) -> None:
    """Идемпотентно: повторный вызов для уже разблокированного титула — no-op
    (кроме, возможно, назначения активным, если он ещё не выбран)."""
    existing = await db.scalar(
        select(CharacterTitle).where(
            CharacterTitle.character_id == character.id, CharacterTitle.title_id == title_id,
        )
    )
    if existing is None:
        db.add(CharacterTitle(character_id=character.id, title_id=title_id))
    if character.active_title_id is None:
        character.active_title_id = title_id


async def has_unlocked(db: AsyncSession, character_id: int, title_id: str) -> bool:
    existing = await db.scalar(
        select(CharacterTitle).where(
            CharacterTitle.character_id == character_id, CharacterTitle.title_id == title_id,
        )
    )
    return existing is not None


def name_of(title_id: str) -> str:
    return TITLE_NAMES.get(title_id, title_id)


def active_title_name(character: Character) -> str | None:
    if character.active_title_id is None:
        return None
    return TITLE_NAMES.get(character.active_title_id)
