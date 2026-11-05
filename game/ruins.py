"""Руины культа: этаж на сетке, ходьба, кубики рун. Чистая логика без БД и VK;
состояние забега - services/ruins_service.py, чат - bot/handlers/ruins.py.

Этаж - связный набор комнат на сетке GRID x GRID. Ходы - между соседними
комнатами (вверх, вниз, влево, вправо). Вход - случайная комната, босс -
самая дальняя от входа по числу шагов (решение владельца). Схемы этажа
игроку не показываем: планировку запоминают сами.

Раскладка хранится в базе как JSON: {"rooms": {"<клетка>": тип}, "start",
"boss", "mobs"}; клетка - номер r * GRID + c.
"""

from __future__ import annotations

import random
from collections import deque

from game.economy import ruins_config as rc

START, FIGHT, ELITE, BOSS = "start", "fight", "elite", "boss"
#: Комнаты с боем - вошёл, бой начинается сразу.
COMBAT_ROOMS = (FIGHT, ELITE, BOSS)

DIRS: dict[str, tuple[int, int]] = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def cell(r: int, c: int) -> int:
    return r * rc.GRID + c


def rc_of(i: int) -> tuple[int, int]:
    return divmod(i, rc.GRID)


def _adjacent(i: int) -> dict[str, int]:
    r, c = rc_of(i)
    out = {}
    for name, (dr, dc) in DIRS.items():
        nr, nc = r + dr, c + dc
        if 0 <= nr < rc.GRID and 0 <= nc < rc.GRID:
            out[name] = cell(nr, nc)
    return out


def rooms_of(layout: dict) -> dict[int, str]:
    return {int(k): v for k, v in layout["rooms"].items()}


def exits(layout: dict, i: int) -> dict[str, int]:
    """Куда можно шагнуть из комнаты i: направление -> комната."""
    rooms = rooms_of(layout)
    return {d: j for d, j in _adjacent(i).items() if j in rooms}


def distances(rooms: set[int], start: int) -> dict[int, int]:
    dist = {start: 0}
    queue = deque([start])
    while queue:
        i = queue.popleft()
        for j in _adjacent(i).values():
            if j in rooms and j not in dist:
                dist[j] = dist[i] + 1
                queue.append(j)
    return dist


def generate(rng: random.Random, floor: int) -> dict:
    """Новый этаж: 5-10 комнат, связных; босс - дальше всех от входа."""
    size = rng.randint(rc.ROOMS_MIN, rc.ROOMS_MAX)
    start = rng.randrange(rc.GRID * rc.GRID)
    taken = {start}
    while len(taken) < size:
        frontier = sorted({j for i in taken for j in _adjacent(i).values()} - taken)
        taken.add(rng.choice(frontier))
    dist = distances(taken, start)
    far = max(dist.values())
    boss = rng.choice(sorted(i for i, d in dist.items() if d == far))
    rooms: dict[str, str] = {}
    for i in sorted(taken):
        if i == start:
            kind = START
        elif i == boss:
            kind = BOSS
        else:
            kind = ELITE if rng.random() < rc.ELITE_SHARE else FIGHT
        rooms[str(i)] = kind
    return {"rooms": rooms, "start": start, "boss": boss, "mobs": rng.randrange(len(rc.MOB_KINDS)), "floor": floor}


def room_kind(layout: dict, i: int) -> str:
    return rooms_of(layout)[i]


def mob_kind(layout: dict) -> tuple[str, str, str, str]:
    return rc.MOB_KINDS[layout.get("mobs", 0) % len(rc.MOB_KINDS)]


def roll_rune_dice(rng: random.Random, floor: int) -> int:
    """Сколько рун выпало с босса этажа одному игроку."""
    return sum(1 for _ in range(rc.rune_dice(floor)) if rng.random() < rc.RUNE_DIE_CHANCE)
