"""Смерть и возрождение (п.5 дизайна, progression-patch-4).

- Время респавна: 1 мин на 1 уровне → 30 мин на MAX_LEVEL (линейно);
- штраф опыта при смерти считается в experience_service.apply_death_penalty
  (20% опыта ТЕКУЩЕГО уровня, без понижения уровня).
"""

from datetime import datetime, timedelta, timezone

from models import Character
from game.combat.formulas import respawn_time_minutes
from services import experience_service


def apply_death(character: Character, now: datetime | None = None) -> int:
    """Применяет последствия смерти: штраф опыта + таймер респавна.
    Возвращает величину потерянного опыта (для лорного сообщения)."""
    now = now or datetime.now(timezone.utc)
    penalty = experience_service.apply_death_penalty(character)
    character.respawn_at = now + timedelta(minutes=respawn_time_minutes(character.level))
    return penalty


def is_dead(character: Character, now: datetime | None = None) -> bool:
    """Персонаж мёртв, пока не наступил respawn_at."""
    if character.respawn_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now < character.respawn_at


def respawn_if_ready(character: Character, now: datetime | None = None) -> bool:
    """Сбрасывает respawn_at, если время вышло. Возвращает True, если ожил."""
    if character.respawn_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now >= character.respawn_at:
        character.respawn_at = None
        return True
    return False
