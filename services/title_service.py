"""Титулы, разблокированные персонажем (патч 23, п.8 — задел; патч 25, п.6:
первое реальное использование помимо стрика ежедневок). Общий разблокиратор
для разных источников наград — не привязан к конкретной механике."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, CharacterTitle

TITLE_NAMES = {
    "relentless": "Неотступный",  # патч 24: 365 дней стрика ежедневок
    "chronicler": "Летописец",  # патч 25: полный сбор Пепельной Песни
    "season_lords": "Владыка Пепла",  # гильдии: лучшая гильдия сезона
    # Секрет: 100 нажатий подряд на тлеющую трещину Монолита на экране
    # персонажа (miniapp BackgroundScene). Нигде не объявляется.
    "attentive": "Внимательный",
}


# Тир титула - как редкость у предметов, только для вида (цвет в профиле).
TIER_ORDER = ("common", "rare", "epic", "legendary")
TITLE_TIERS = {
    "chronicler": "rare",
    "season_lords": "epic",
    "relentless": "legendary",
    "attentive": "legendary",
}


def tier_of(title_id: str | None) -> str | None:
    if title_id is None:
        return None
    return TITLE_TIERS.get(title_id, "common")


async def unlocked_ids(db: AsyncSession, character_id: int) -> list[str]:
    return list(
        (
            await db.scalars(
                select(CharacterTitle.title_id).where(CharacterTitle.character_id == character_id)
                .order_by(CharacterTitle.unlocked_at, CharacterTitle.id)
            )
        ).all()
    )


async def menu(db: AsyncSession, character: Character) -> list[dict]:
    """Открытые титулы для выбора: сначала самые редкие."""
    ids = [t for t in await unlocked_ids(db, character.id) if t in TITLE_NAMES]
    ids.sort(key=lambda t: -TIER_ORDER.index(tier_of(t)))
    return [
        {"id": t, "name": TITLE_NAMES[t], "tier": tier_of(t), "active": t == character.active_title_id}
        for t in ids
    ]


async def set_active(db: AsyncSession, character: Character, title_id: str | None) -> bool:
    """Носить титул (или None - без титула). Только из открытых."""
    if title_id is not None and (title_id not in TITLE_NAMES or not await has_unlocked(db, character.id, title_id)):
        return False
    character.active_title_id = title_id
    return True


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
