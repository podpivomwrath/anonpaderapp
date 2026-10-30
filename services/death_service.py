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
    from services import pk_service

    now = now or datetime.now(timezone.utc)
    # Кровавое клеймо 3+: смерть отнимает больше опыта.
    penalty = 0
    if not tincture_active(character, now):
        penalty = experience_service.apply_death_penalty(character, pk_service.death_xp_mult(character))
    character.respawn_at = now + timedelta(minutes=_respawn_minutes(character))
    return penalty


def apply_pvp_death(character: Character, now: datetime | None = None) -> None:
    """Поражение в открытом PvP (патч 22): таймер респавна как при обычной
    смерти, но БЕЗ штрафа опыта — цена поражения уже уплачена трофеями."""
    from services import pk_service

    now = now or datetime.now(timezone.utc)
    # Кровавое клеймо 3+: и в PvP смерть стоит опыта (обычно - нет).
    if pk_service.costly_death(character) and not tincture_active(character, now):
        experience_service.apply_death_penalty(character, pk_service.death_xp_mult(character))
    character.respawn_at = now + timedelta(minutes=_respawn_minutes(character))


def tincture_active(character: Character, now: datetime | None = None) -> bool:
    """Настойка пепла (товар за самоцветы): пока действует, смерть не
    отнимает опыт."""
    until = character.ash_tincture_until
    if until is None:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) < until


def _respawn_minutes(character: Character) -> float:
    """Часовня гильдии и древо сокращают ожидание, Дар первопроходцев -
    ещё вдвое (2026-10-30)."""
    from game.economy import prerelease_config
    from services import guild_territory_service

    return (respawn_time_minutes(character.level) * guild_territory_service.respawn_multiplier(character)
            * prerelease_config.respawn_mult())


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
