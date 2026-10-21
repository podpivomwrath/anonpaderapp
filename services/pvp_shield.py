"""Щит от нападения игроков на пару минут (против PvP-снайпинга).

Даётся после ничьей (той стороне, на которую напали), на выходе из разлома
и рейда, при входе на клетку Монолита (2026-10-18, решение владельца)
и после возрождения у часовни гильдии (2026-10-21):
игроки должны успеть уйти или собраться в рейд, а не ловиться на выходе.
Напал сам - щит теряешь. Ушёл с клетки, где его получил, - тоже
(2026-10-18): щит, чтобы уйти, а не чтобы с ним гулять.

В памяти: две минуты рестарт переживать не обязаны.
"""

import time

from game.combat import balance_config as bc

DRAW = "после ничьей"
RIFT = "после разлома"
RAID = "после рейда"
MONOLITH = "у Монолита"
CHAPEL = "после возрождения"

# character_id -> (до какого time.time(), причина, клетка, где выдан)
_shields: dict[int, tuple[float, str, tuple[int, int] | None]] = {}


def grant(
    character_id: int, reason: str, seconds: int = bc.PVP_SAFE_SECONDS,
    cell: tuple[int, int] | None = None,
) -> None:
    """Щит не укорачивается: если уже действует дольше, оставляем его.
    cell - клетка, с которой уходить нельзя без потери щита."""
    until = time.time() + seconds
    current = _shields.get(character_id)
    if current is None or current[0] < until:
        _shields[character_id] = (until, reason, cell)


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
    """Персонаж ступил на клетку: ушёл с клетки щита - щит пропал;
    пришёл на Монолит - новый щит."""
    here = (character.pos_x, character.pos_y)
    entry = _shields.get(getattr(character, "id", None))
    if entry is not None and entry[2] is not None and entry[2] != here:
        _shields.pop(character.id, None)
    if here == (0, 0):
        grant(character.id, MONOLITH, cell=here)
