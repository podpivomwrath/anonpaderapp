"""Призрачная гончая (питомец, 2026-11-12): чует Кровавое клеймо. В сводке
клетки - строка, где ближайший игрок с клеймом (bot/world_summary.py).

Сводка синхронная и в базу не ходит, поэтому клеймёные собираются отдельным
обходом раз в REFRESH_SECONDS: их немного, а сводок много.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from bot import pet_texts
from game.economy import pet_config as pc
from models import Character, CharacterVoyage
from services import death_service, pk_service, ruins_service
from services.db import get_session_factory

REFRESH_SECONDS = 20

#: (id, имя, x, y) всех, кто сейчас с клеймом.
_branded: list[tuple[int, str, int, int]] = []


async def refresh() -> int:
    global _branded
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        hidden = set((await db.scalars(ruins_service.inside_query())).all())
        hidden |= set((await db.scalars(
            select(CharacterVoyage.character_id).where(CharacterVoyage.status == "away"))).all())
        rows = (await db.scalars(select(Character).where(
            Character.pk_marks > 0, Character.creation_state.is_(None),
        ))).all()
    _branded = [
        (c.id, c.name, c.pos_x, c.pos_y) for c in rows
        if c.id not in hidden and not death_service.is_dead(c)
        and pk_service.marks(c, now) >= pc.HOUND_MIN_MARKS
    ]
    return len(_branded)


def line_for(character) -> str | None:
    """Строка гончей в сводку; None - гончей нет или клеймёных нет."""
    if getattr(character, "pet_id", None) != pc.HOUND:
        return None
    x, y = character.pos_x, character.pos_y
    best = None
    for cid, name, bx, by in _branded:
        if cid == character.id:
            continue
        dist = max(abs(bx - x), abs(by - y))
        if best is None or dist < best[0]:
            best = (dist, name, bx - x, by - y)
    if best is None:
        return None
    return pet_texts.hound_line(best[1], best[2], best[3])
