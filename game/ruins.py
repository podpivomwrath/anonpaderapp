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
AMBUSH = "ambush"            # бой без зелий
SPRING = "spring"            # источник: лечение или дар
ALTAR = "altar"              # кровь за дар
EVENT = "event"              # сценка с выбором
TRAP = "trap"                # проверка ловкости, срабатывает сама
CRYPT = "crypt"              # поднять павших за здоровье живых
WELL = "well"                # сменить дар
CAVEIN = "cavein"            # обвал: пролезть с уроном или обойти боем
PRISONER = "prisoner"        # пленник: бой с охраной за дар
STOREROOM = "storeroom"      # кладовая: реликвии + проклятие на этаж
CHAPEL = "chapel"            # молельня: реликвии из мешка за редкий дар
TREASURE = "treasure"        # тайник: реликвии, иногда мимик
#: Комнаты с боем - вошёл, бой начинается сразу.
COMBAT_ROOMS = (FIGHT, ELITE, BOSS, AMBUSH)
#: Комнаты, где лидер выбирает, что делать (кнопки), - до выбора одна.
CHOICE_ROOMS = (SPRING, ALTAR, EVENT, CRYPT, WELL, CAVEIN, PRISONER, STOREROOM, CHAPEL, TREASURE)
#: Вес типа комнаты на этаже (вход и босс - отдельно).
ROOM_WEIGHTS: dict[str, int] = {
    FIGHT: 34, ELITE: 15, AMBUSH: 6, SPRING: 6, ALTAR: 4, EVENT: 8, TRAP: 6, CRYPT: 3, WELL: 3,
    CAVEIN: 4, PRISONER: 4, STOREROOM: 3, CHAPEL: 3, TREASURE: 6,
}

#: Комнаты, которые встречаются раз за заход (репорт 339: пленник-забойщик -
#: один человек, а попадался по два раза на этаже).
ONCE_PER_RUN = (PRISONER,)

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


def generate(rng: random.Random, floor: int, used: tuple[str, ...] | list[str] = ()) -> dict:
    """Новый этаж: 5-10 комнат, связных; босс - дальше всех от входа.
    used - комнаты из ONCE_PER_RUN, что уже были в этом заходе."""
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
    banned = set(used)
    for i in sorted(taken):
        if i == start:
            kind = START
        elif i == boss:
            kind = BOSS
        else:
            kinds = [k for k in ROOM_WEIGHTS if k not in banned]
            kind = rng.choices(kinds, weights=[ROOM_WEIGHTS[k] for k in kinds])[0]
            if kind in ONCE_PER_RUN:
                banned.add(kind)
        rooms[str(i)] = kind
    from game import ruins_rooms  # цикл импортов

    events = {k: ruins_rooms.event_for(rng) for k, v in rooms.items() if v == EVENT}
    return {"rooms": rooms, "start": start, "boss": boss, "mobs": rng.randrange(len(rc.MOB_KINDS)), "floor": floor,
            "events": events}


def once_rooms(layout: dict, used: tuple[str, ...] | list[str] = ()) -> list[str]:
    """used плюс комнаты ONCE_PER_RUN этого этажа - для следующего generate."""
    here = set(rooms_of(layout).values())
    return sorted(set(used) | {k for k in ONCE_PER_RUN if k in here})


def event_of(layout: dict, i: int) -> str | None:
    return (layout.get("events") or {}).get(str(i))


def room_kind(layout: dict, i: int) -> str:
    return rooms_of(layout)[i]


def mob_kind(layout: dict) -> tuple[str, str, str, str]:
    return rc.MOB_KINDS[layout.get("mobs", 0) % len(rc.MOB_KINDS)]


def roll_rune_dice(rng: random.Random, floor: int) -> int:
    """Сколько рун выпало с босса этажа одному игроку."""
    return sum(1 for _ in range(rc.rune_dice(floor)) if rng.random() < rc.rune_die_chance(floor))
