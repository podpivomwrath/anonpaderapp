"""Смерть и возрождение (п.5 дизайна)."""

from datetime import datetime, timedelta, timezone

from game.combat import balance_config as bc
from services.death_service import apply_death, is_dead, respawn_if_ready

NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


async def test_death_costs_experience_and_time(db_session, make_character) -> None:
    character = await make_character(level=1, experience=1000)
    apply_death(character, now=NOW)
    assert character.experience == 800  # -20% опыта текущего уровня
    assert character.respawn_at == NOW + timedelta(minutes=1)  # 1 мин на 1 ур.


async def test_respawn_time_scales_with_level(db_session, make_character) -> None:
    character = await make_character(level=bc.MAX_LEVEL)
    apply_death(character, now=NOW)
    assert character.respawn_at == NOW + timedelta(minutes=30)  # 30 мин на MAX_LEVEL


async def test_dead_then_respawn(db_session, make_character) -> None:
    character = await make_character(level=1)
    apply_death(character, now=NOW)
    assert is_dead(character, now=NOW + timedelta(seconds=30))
    assert not respawn_if_ready(character, now=NOW + timedelta(seconds=30))
    assert respawn_if_ready(character, now=NOW + timedelta(minutes=2))
    assert character.respawn_at is None
    assert not is_dead(character, now=NOW + timedelta(minutes=2))
