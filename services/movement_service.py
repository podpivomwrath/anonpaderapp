"""Перемещение по клетке карты: занимает время (world_config.CELL_TRAVEL_SECONDS).

Во время перемещения действия недоступны — движки боя/города должны сами
проверять is_traveling перед тем, как разрешать действие.
"""

from datetime import datetime, timedelta, timezone

from game.world import grid
from game.world import world_config as wc
from models import Character
from services import crown_service


def start_travel(
    character: Character, dx: int, dy: int, now: datetime | None = None
) -> float:
    """Возвращает длительность перехода в секундах.

    Именно возвращает, а не оставляет вызывающему брать константу: с венцом
    «Трофей» (патч 91) переход короче, и планировщик прибытия обязан знать
    ТУ ЖЕ величину, что записана в travel_arrives_at. Иначе игрок приходит по
    часам базы, а сообщение о прибытии ждёт полную десятку секунд.
    """
    now = now or datetime.now(timezone.utc)
    seconds = wc.CELL_TRAVEL_SECONDS * crown_service.travel_multiplier(character)
    character.travel_target_x = grid.clamp(character.pos_x + dx)
    character.travel_target_y = grid.clamp(character.pos_y + dy)
    character.travel_arrives_at = now + timedelta(seconds=seconds)
    return seconds


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


def cancel_travel(character: Character) -> None:
    """Принудительно отменяет поездку (патч 25, п.5: /застрял) — персонаж
    остаётся там, где уже был (pos_x/y не менялись во время пути), путь к
    цели просто не завершается."""
    character.travel_target_x = None
    character.travel_target_y = None
    character.travel_arrives_at = None


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
