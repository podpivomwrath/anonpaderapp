"""Пепельная Песнь — сбор 10 обрывков + прочтение у Пепельного алтаря
(патч 25, п.6). Флейвор-выбор обрывка (какой текст показать) остаётся
случайным (game/world/flavor.py, atmosphere-patch-3) — этот сервис только
ОТМЕЧАЕТ, какие индексы игрок уже видел, и разруливает завершение/награду."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.world.flavor import song_part_count, song_parts
from models import Character, CharacterSongFragment
from services import mount_service, title_service

TITLE_ID = "chronicler"
MOUNT_ID = "ashen_steed"


async def record_seen(db: AsyncSession, character: Character, index: int) -> None:
    existing = await db.scalar(
        select(CharacterSongFragment).where(
            CharacterSongFragment.character_id == character.id,
            CharacterSongFragment.fragment_index == index,
        )
    )
    if existing is None:
        db.add(CharacterSongFragment(character_id=character.id, fragment_index=index))
        await db.flush()


async def seen_indices(db: AsyncSession, character_id: int) -> set[int]:
    rows = (
        await db.scalars(
            select(CharacterSongFragment.fragment_index).where(
                CharacterSongFragment.character_id == character_id
            )
        )
    ).all()
    return set(rows)


async def is_complete(db: AsyncSession, character_id: int) -> bool:
    return len(await seen_indices(db, character_id)) >= song_part_count()


async def already_read(db: AsyncSession, character_id: int) -> bool:
    return await title_service.has_unlocked(db, character_id, TITLE_ID)


async def can_read(db: AsyncSession, character_id: int) -> bool:
    if await already_read(db, character_id):
        return False
    return await is_complete(db, character_id)


async def read_song(db: AsyncSession, character: Character) -> bool:
    """Разово: титул «Летописец» + маунт «Пепельный скакун». True — реально
    выдано этим вызовом (idempotent — повторное чтение недоступно)."""
    if await already_read(db, character.id):
        return False
    await title_service.unlock(db, character, TITLE_ID)
    await mount_service.grant(db, character, MOUNT_ID)
    return True


@dataclass
class SongProgress:
    total: int
    seen: set[int]
    complete: bool
    read: bool


async def get_progress(db: AsyncSession, character_id: int) -> SongProgress:
    seen = await seen_indices(db, character_id)
    total = song_part_count()
    return SongProgress(
        total=total, seen=seen, complete=len(seen) >= total,
        read=await already_read(db, character_id),
    )


@dataclass
class SongFragmentDisplay:
    index: int
    seen: bool
    text: str | None  # None — ещё не увиден («???» — дело фронтенда)


async def fragments_display(db: AsyncSession, character_id: int) -> list[SongFragmentDisplay]:
    """Для мини-аппа (патч 25, п.6): собранные обрывки с текстом, несобранные
    без текста (фронтенд рисует заглушку «???»)."""
    seen = await seen_indices(db, character_id)
    return [
        SongFragmentDisplay(index=i, seen=i in seen, text=part if i in seen else None)
        for i, part in enumerate(song_parts())
    ]
