"""Ключ Монолита виден в общем статусе - в городе, в пути и в поле
(2026-10-30: в городе строки не было, игрок увидел ключ только после смерти)."""

import random

from sqlalchemy import select

from bot import world_summary
from models import CharacterStats


async def test_key_in_status_lines_and_summary_once(db_session, make_character) -> None:
    character = await make_character(level=20)
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    assert "Ключ Монолита" not in world_summary.status_lines(character, stats, 0)
    character.raid_keys = 2
    character.pos_x, character.pos_y = 10, 10
    assert "🗝 Ключ Монолита ×2" in world_summary.status_lines(character, stats, 0)
    summary = world_summary.location_summary(character, stats, random.Random(1), 0)
    assert summary.count("Ключ Монолита") == 1
