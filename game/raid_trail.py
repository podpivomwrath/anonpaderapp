"""Лабиринт «Тропы Безымянного» (2026-10-20): чистая логика без VK.

Поле SIZE×SIZE, стены между клетками. Лабиринт строится как идеальный (путь
до каждой клетки ровно один), потом в нём прорубается несколько лишних
проходов, чтобы было из чего выбирать. Одна ветка закрыта решёткой - она
поднимается, когда обе плиты держат одновременно; за решёткой лежит один из
трёх Следов. Безымянный бродит по коридорам и раз в tc.HUNTER_STEP_SECONDS
делает шаг к ближайшему игроку.

Время - аргумент now (секунды, монотонные), чтобы всё проверялось тестами.
"""

import random
from collections import deque
from dataclasses import dataclass, field

from game.economy import raid_trail_config as tc

N = tc.SIZE
START, GATE = 0, N * N - 1
DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
DIR_ARROWS = {"up": "⬆️", "down": "⬇️", "left": "⬅️", "right": "➡️"}

FOOTPRINT, PLATE, PIT, REST, ECHO = "footprint", "plate", "pit", "rest", "echo"

#: Места лабиринта: название клетки -> группа картинки. Названия нужны, чтобы
#: группа договаривалась словами («я у колодца»), а не координатами.
PLACE_NAMES = {
    "well": ("Сухой колодец", "Колодец с цепью", "Двор с колодцем", "Глухой двор", "Каменный желоб", "Водосборник"),
    "bells": ("Зал колоколов", "Колокольня", "Зал без звона", "Колокольный проход", "Медный зал", "Зал цепей"),
    "arch": ("Обвалившаяся арка", "Узкий лаз", "Треснувший свод", "Завал", "Арка без имени", "Кривой коридор"),
    "lists": ("Комната списков", "Стена имён", "Зал вычеркнутых", "Зал записей", "Переписная", "Пыльная канцелярия"),
}


def rc(i: int) -> tuple[int, int]:
    return divmod(i, N)


def idx(r: int, c: int) -> int:
    return r * N + c


def neighbors(i: int) -> dict[str, int]:
    r, c = rc(i)
    out = {}
    for name, (dr, dc) in DIRS.items():
        nr, nc = r + dr, c + dc
        if 0 <= nr < N and 0 <= nc < N:
            out[name] = idx(nr, nc)
    return out


def _edge(a: int, b: int) -> frozenset:
    return frozenset((a, b))


@dataclass
class Maze:
    passages: set[frozenset]
    grate: frozenset
    locked: set[int]
    kinds: dict[int, str]
    names: dict[int, str]
    places: dict[int, str]

    def connected(self, a: int, b: int, grate_open: bool) -> bool:
        e = _edge(a, b)
        if e not in self.passages:
            return False
        return grate_open or e != self.grate


def _perfect_tree(rng: random.Random) -> tuple[set[frozenset], dict[int, int]]:
    """Идеальный лабиринт обходом в глубину от старта: ходы и родитель клетки."""
    passages: set[frozenset] = set()
    parent = {START: -1}
    stack = [START]
    while stack:
        cur = stack[-1]
        options = [n for n in neighbors(cur).values() if n not in parent]
        if not options:
            stack.pop()
            continue
        nxt = rng.choice(options)
        parent[nxt] = cur
        passages.add(_edge(cur, nxt))
        stack.append(nxt)
    return passages, parent


def _subtree(parent: dict[int, int], root: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for child, par in parent.items():
        children.setdefault(par, []).append(child)
    out, stack = set(), [root]
    while stack:
        cur = stack.pop()
        out.add(cur)
        stack.extend(children.get(cur, ()))
    return out


def _bfs(maze_passages, start: int, blocked: frozenset | None = None) -> dict[int, int]:
    dist = {start: 0}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for n in neighbors(cur).values():
            e = _edge(cur, n)
            if n in dist or e not in maze_passages or e == blocked:
                continue
            dist[n] = dist[cur] + 1
            queue.append(n)
    return dist


def _bfs_avoiding(passages, start: int, avoid: set[int]) -> set[int]:
    """Клетки, достижимые от start, не заходя в avoid (решётка открыта)."""
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for n in neighbors(cur).values():
            if n not in seen and n not in avoid and _edge(cur, n) in passages:
                seen.add(n)
                queue.append(n)
    return seen


def generate(rng: random.Random) -> Maze:
    start_exits = set(neighbors(START).values())
    while True:
        while True:
            passages, parent = _perfect_tree(rng)
            candidates = []
            for v, u in parent.items():
                if u < 0:
                    continue
                sub = _subtree(parent, v)
                # Соседи входа - не за решёткой: оба хода со старта открыты всегда.
                if tc.LOCKED_MIN <= len(sub) <= tc.LOCKED_MAX and not sub & ({START, GATE} | start_exits):
                    candidates.append((_edge(u, v), sub))
            if candidates:
                break
        grate, locked = rng.choice(candidates)
        # Лишние проходы - только внутри своей части, чтобы не обойти решётку.
        extra = [
            _edge(a, b) for a in range(N * N) for b in neighbors(a).values()
            if a < b and _edge(a, b) not in passages and ((a in locked) == (b in locked))
        ]
        rng.shuffle(extra)
        passages |= set(extra[: tc.EXTRA_OPENINGS])
        # Со входа - два хода (2026-10-21): с одним Безымянный запирал группу на старте.
        passages |= {_edge(START, n) for n in start_exits}

        # Каждый ход со входа сам ведёт к Воротам: Безымянный в одном не запрёт.
        if all(GATE in _bfs_avoiding(passages, START, {n}) for n in start_exits if n != GATE):
            break

    kinds: dict[int, str] = {}
    dist = _bfs(passages, START, blocked=grate)
    outside = [i for i in range(N * N) if i not in locked and i not in (START, GATE)]
    kinds[rng.choice(sorted(locked))] = FOOTPRINT
    far = sorted(outside, key=lambda i: -dist.get(i, 0))
    for i in rng.sample(far[: max(6, len(far) // 2)], tc.FOOTPRINTS - 1):
        kinds[i] = FOOTPRINT
    free = [i for i in outside if i not in kinds]
    # Плиты - как можно дальше друг от друга: держать их должны двое разными концами.
    best = max(
        ((a, b) for a in free for b in free if a < b),
        key=lambda ab: (abs(rc(ab[0])[0] - rc(ab[1])[0]) + abs(rc(ab[0])[1] - rc(ab[1])[1]), rng.random()),
    )
    kinds[best[0]] = kinds[best[1]] = PLATE
    free = [i for i in free if i not in kinds]
    rng.shuffle(free)
    # Яма отбрасывает на старт - в единственном коридоре к чему-то она сделала
    # бы это «что-то» недостижимым. Ставим только туда, без чего всё остальное
    # по-прежнему достижимо.
    # Не у входа (2026-10-22, жалоба «второй выход ведёт сразу в могилу»): на
    # соседях входа ям нет никогда, через клетку от него - только если больше
    # некуда.
    def from_start(i: int) -> int:
        return sum(rc(i))

    pits: set[int] = set()
    for i in sorted((i for i in free if from_start(i) > 1), key=lambda i: from_start(i) <= 2):
        if len(pits) == tc.PITS:
            break
        trial = pits | {i}
        if len(_bfs_avoiding(passages, START, trial)) == N * N - len(trial):
            pits.add(i)
            free.remove(i)
    for i in pits:
        kinds[i] = PIT
    for kind in (REST, ECHO):
        kinds[free.pop()] = kind

    places: dict[int, str] = {}
    names: dict[int, str] = {}
    pools = {group: list(titles) for group, titles in PLACE_NAMES.items()}
    for pool in pools.values():
        rng.shuffle(pool)
    groups = list(PLACE_NAMES)
    for i in range(N * N):
        group = rng.choice(groups)
        places[i] = group
        names[i] = pools[group].pop() if pools[group] else PLACE_NAMES[group][0]
    names[START], names[GATE] = "Вход", "Ворота"
    return Maze(passages=passages, grate=grate, locked=locked, kinds=kinds, names=names, places=places)


# --- Состояние захода --------------------------------------------------------------


@dataclass
class MoveResult:
    ok: bool
    #: frozen | not_adjacent | wall | grate | done
    reason: str = ""
    events: list[str] = field(default_factory=list)
    echo: str = ""


@dataclass
class HunterResult:
    moved: bool = False
    caught: list[int] = field(default_factory=list)
    near: list[int] = field(default_factory=list)


def compass(frm: int, to: int) -> str:
    (r1, c1), (r2, c2) = rc(frm), rc(to)
    parts = []
    if r2 < r1:
        parts.append("север")
    elif r2 > r1:
        parts.append("юг")
    if c2 > c1:
        parts.append("восток")
    elif c2 < c1:
        parts.append("запад")
    return "-".join(parts) if parts else "здесь"


class Labyrinth:
    def __init__(self, players: list[int], rng: random.Random, now: float = 0.0) -> None:
        self.rng = rng
        self.maze = generate(rng)
        self.players = list(players)
        self.pos = {cid: START for cid in self.players}
        self.frozen_until: dict[int, float] = {}
        self.explored: set[int] = {START}
        self.found: set[int] = set()
        self.rest_used = False
        self.grate_open = False
        self.plate_seen: dict[int, float] = {}
        self.hunter = GATE
        self.hunter_next = now + tc.HUNTER_GRACE_SECONDS
        self.solo = len(self.players) == 1
        a, b = [i for i, k in self.maze.kinds.items() if k == PLATE]
        steps = _bfs(self.maze.passages, a, blocked=self.maze.grate).get(b, N * N)
        self.plate_hold = (
            steps * tc.PLATE_HOLD_SOLO_PER_STEP + tc.PLATE_HOLD_SOLO_EXTRA if self.solo else tc.PLATE_HOLD_GROUP
        )

    # --- карта ---

    def kind(self, i: int) -> str | None:
        return self.maze.kinds.get(i)

    def exits(self, i: int) -> list[str]:
        return [d for d, n in neighbors(i).items() if self.maze.connected(i, n, self.grate_open)]

    def footprints_left(self) -> list[int]:
        return [i for i, k in self.maze.kinds.items() if k == FOOTPRINT and i not in self.found]

    def is_frozen(self, cid: int, now: float) -> bool:
        return self.frozen_until.get(cid, 0.0) > now

    def hunter_near(self, cid: int) -> bool:
        """Безымянного слышно, если он через стенку или в соседнем проходе."""
        here = self.pos[cid]
        return self.hunter == here or self.hunter in neighbors(here).values()

    # --- плиты ---

    def update_plates(self, now: float) -> bool:
        """True - решётка только что поднялась."""
        plates = [i for i, k in self.maze.kinds.items() if k == PLATE]
        for p in plates:
            if p in self.pos.values():
                self.plate_seen[p] = now
        if not self.grate_open and all(now - self.plate_seen.get(p, -1e9) <= self.plate_hold for p in plates):
            self.grate_open = True
            return True
        return False

    # --- ход игрока ---

    def check(self, cid: int, target: int, now: float) -> str | None:
        """Почему шаг невозможен (None - можно). Шаг идёт tc.STEP_SECONDS:
        проверка - при нажатии, сам move - когда игрок дошёл."""
        if self.is_frozen(cid, now):
            return "frozen"
        here = self.pos[cid]
        if target not in neighbors(here).values():
            return "not_adjacent"
        e = _edge(here, target)
        if e not in self.maze.passages:
            return "wall"
        if e == self.maze.grate and not self.grate_open:
            return "grate"
        return None

    def move(self, cid: int, target: int, now: float) -> MoveResult:
        reason = self.check(cid, target, now)
        if reason:
            return MoveResult(False, reason)
        self.pos[cid] = target
        self.explored.add(target)
        out = MoveResult(True)
        kind = self.kind(target)
        if kind == FOOTPRINT and target not in self.found:
            self.found.add(target)
            out.events.append("footprint")
        elif kind == PIT:
            self.pos[cid] = START
            out.events.append("pit")
        elif kind == REST and not self.rest_used:
            self.rest_used = True
            out.events.append("rest")
        elif kind == ECHO:
            left = self.footprints_left()
            if left:
                nearest = min(left, key=lambda i: abs(rc(i)[0] - rc(target)[0]) + abs(rc(i)[1] - rc(target)[1]))
                out.echo = compass(target, nearest)
            out.events.append("echo")
        if self.pos[cid] == self.hunter and target != GATE:
            self._catch(cid, now)
            out.events.append("caught")
        if self.update_plates(now):
            out.events.append("grate")
        return out

    def _catch(self, cid: int, now: float) -> None:
        self.frozen_until[cid] = now + tc.CAUGHT_SECONDS

    def release(self, now: float) -> list[int]:
        """Пойманные, чьё время вышло, - на старт."""
        back = [cid for cid, until in self.frozen_until.items() if until <= now]
        for cid in back:
            self.frozen_until.pop(cid)
            self.pos[cid] = START
        return back

    # --- Безымянный ---

    def hunter_can_enter(self, i: int) -> bool:
        """Безымянный не заходит на ворота (там ждут своих) и в ямы: раньше
        шагал в провал и стоял в нём (2026-10-22)."""
        return i != GATE and self.kind(i) != PIT

    def hunter_tick(self, now: float) -> HunterResult:
        out = HunterResult()
        if now < self.hunter_next:
            return out
        self.hunter_next = now + tc.HUNTER_STEP_SECONDS
        # Вход и ворота - убежища: у ворот группа ждёт отставших (2026-10-22,
        # жалоба: ждали у ворот, а он ловил там по одному, пока не вышло время).
        prey = [
            cid for cid in self.players
            if not self.is_frozen(cid, now) and self.pos[cid] not in (START, GATE)
        ]
        if not prey:
            return out
        # Кратчайший путь до ближайшей добычи - BFS от Безымянного.
        prev = {self.hunter: None}
        queue = deque([self.hunter])
        targets = {self.pos[c] for c in prey}
        goal = None
        while queue:
            cur = queue.popleft()
            if cur in targets and cur != self.hunter:
                goal = cur
                break
            for n in neighbors(cur).values():
                if n not in prev and self.hunter_can_enter(n) and self.maze.connected(cur, n, self.grate_open):
                    prev[n] = cur
                    queue.append(n)
        if goal is None:
            return out
        step = goal
        while prev[step] != self.hunter:
            step = prev[step]
        self.hunter = step
        out.moved = True
        for cid in prey:
            if self.pos[cid] == self.hunter:
                self._catch(cid, now)
                out.caught.append(cid)
            elif self.hunter_near(cid):
                out.near.append(cid)
        return out

    # --- итог ---

    def done(self, now: float) -> bool:
        return (
            not self.footprints_left()
            and all(self.pos[c] == GATE and not self.is_frozen(c, now) for c in self.players)
        )
