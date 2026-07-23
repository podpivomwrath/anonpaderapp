"""Перемещение по клетке карты: занимает время (world_config.CELL_TRAVEL_SECONDS).

Во время перемещения действия недоступны — движки боя/города должны сами
проверять is_traveling перед тем, как разрешать действие.
"""

from datetime import datetime, timedelta, timezone

from game.world import grid
from game.world import world_config as wc
from models import Character


def start_travel(
    character: Character, dx: int, dy: int, now: datetime | None = None
) -> None:
    now = now or datetime.now(timezone.utc)
    character.travel_target_x = grid.clamp(character.pos_x + dx)
    character.travel_target_y = grid.clamp(character.pos_y + dy)
    character.travel_arrives_at = now + timedelta(seconds=wc.CELL_TRAVEL_SECONDS)


def is_traveling(character: Character, now: datetime | None = None) -> bool:
    if character.travel_arrives_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now < character.travel_arrives_at


def remaining_seconds(character: Character, now: datetime | None = None) -> float:
    if character.travel_arrives_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    return max((character.travel_arrives_at - now).total_seconds(), 0.0)


def resolve_arrival(character: Character, now: datetime | None = None) -> bool:
    """Применяет прибытие, если время в пути истекло. True — применено."""
    if character.travel_arrives_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    if now < character.travel_arrives_at:
        return False
    character.pos_x = character.travel_target_x
    character.pos_y = character.travel_target_y
    character.travel_target_x = None
    character.travel_target_y = None
    character.travel_arrives_at = None
    return True
