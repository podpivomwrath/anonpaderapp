"""Перемещение по клетке: занимает время, блокирует до истечения."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from game.world import world_config as wc
from services import movement_service as svc

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeCharacter:
    pos_x: int
    pos_y: int
    travel_target_x: int | None = None
    travel_target_y: int | None = None
    travel_arrives_at: datetime | None = None


def test_start_travel_sets_target_and_timer() -> None:
    char = FakeCharacter(pos_x=0, pos_y=0)
    svc.start_travel(char, 0, 1, now=NOW)
    assert (char.travel_target_x, char.travel_target_y) == (0, 1)
    assert char.travel_arrives_at == NOW + timedelta(seconds=wc.CELL_TRAVEL_SECONDS)


def test_start_travel_clamped_to_bounds() -> None:
    char = FakeCharacter(pos_x=50, pos_y=50)
    svc.start_travel(char, 1, 1, now=NOW)  # попытка выйти за границу карты
    assert (char.travel_target_x, char.travel_target_y) == (wc.BOUNDS_MAX, wc.BOUNDS_MAX)


def test_is_traveling_before_and_after_arrival() -> None:
    char = FakeCharacter(pos_x=0, pos_y=0)
    svc.start_travel(char, 1, 0, now=NOW)
    assert svc.is_traveling(char, now=NOW + timedelta(seconds=1))
    assert not svc.is_traveling(char, now=NOW + timedelta(seconds=wc.CELL_TRAVEL_SECONDS))


def test_remaining_seconds_counts_down() -> None:
    char = FakeCharacter(pos_x=0, pos_y=0)
    svc.start_travel(char, 1, 0, now=NOW)
    left = svc.remaining_seconds(char, now=NOW + timedelta(seconds=4))
    assert left == wc.CELL_TRAVEL_SECONDS - 4


def test_resolve_arrival_only_after_time_elapsed() -> None:
    char = FakeCharacter(pos_x=0, pos_y=0)
    svc.start_travel(char, 2, -1, now=NOW)

    assert not svc.resolve_arrival(char, now=NOW + timedelta(seconds=1))
    assert char.pos_x == 0  # ещё не применилось

    applied = svc.resolve_arrival(char, now=NOW + timedelta(seconds=wc.CELL_TRAVEL_SECONDS))
    assert applied
    assert (char.pos_x, char.pos_y) == (2, -1)
    assert char.travel_arrives_at is None  # состояние в пути очищено


def test_resolve_arrival_false_when_not_traveling() -> None:
    char = FakeCharacter(pos_x=5, pos_y=5)
    assert not svc.resolve_arrival(char, now=NOW)
