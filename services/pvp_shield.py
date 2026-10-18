"""Щит от нападения игроков на пару минут (против PvP-снайпинга).

Даётся после ничьей (той стороне, на которую напали), на выходе из разлома
и рейда и при входе на клетку Монолита (2026-10-18, решение владельца):
игроки должны успеть уйти или собраться в рейд, а не ловиться на выходе.
Напал сам - щит теряешь.

В памяти: две минуты рестарт переживать не обязаны.
"""

import time

from game.combat import balance_config as bc

DRAW = "после ничьей"
RIFT = "после разлома"
RAID = "после рейда"
MONOLITH = "у Монолита"

# character_id -> (до какого time.time(), причина)
_shields: dict[int, tuple[float, str]] = {}


def grant(character_id: int, reason: str, seconds: int = bc.PVP_SAFE_SECONDS) -> None:
    """Щит не укорачивается: если уже действует дольше, оставляем его."""
    until = time.time() + seconds
    current = _shields.get(character_id)
    if current is None or current[0] < until:
        _shields[character_id] = (until, reason)


def left(character_id: int) -> tuple[int, str]:
    """(сколько секунд ещё действует, причина); (0, "") - щита нет."""
    entry = _shields.get(character_id)
    if entry is None:
        return 0, ""
    remaining = entry[0] - time.time()
    if remaining <= 0:
        _shields.pop(character_id, None)
        return 0, ""
    return int(remaining) + 1, entry[1]


def drop(character_id: int) -> None:
    _shields.pop(character_id, None)


def on_moved(character) -> None:
    """Вызывается, когда персонаж ступил на клетку: на Монолите - щит."""
    if (character.pos_x, character.pos_y) == (0, 0):
        grant(character.id, MONOLITH)
