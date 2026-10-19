"""Рейд «Жернова Паломников», этап 1: шествие (не бой).

Барабан бьёт ритм из mc.BAR_BEATS ударов - «левой», «правой» или «замри».
Каждому участнику видна только часть ударов такта, остальные - «?»: ритм
собирают вместе в чате. Удар идёт, когда шаг выбрали все живые. Все верно -
колонна делает шаг. Кто ошибся - получает стак хромоты и шаг пропадает; на
mc.LAME_LIMIT стаках игрок падает, колонна ждёт его и откатывается на
mc.LAG_STEPS_LOST шагов, а хромота с него сходит.

Чистая логика, без VK: оркестрация - bot/handlers/raid_procession.py.
"""

import random
from dataclasses import dataclass, field

from game.economy import raid_mill_config as mc

LEFT, RIGHT, HOLD = "left", "right", "hold"
MOVES = (LEFT, RIGHT, HOLD)
MOVE_WORD = {LEFT: "Левой", RIGHT: "Правой", HOLD: "Замри"}


def new_pattern(rng: random.Random) -> list[str]:
    """Такт без четырёх одинаковых ударов - иначе нечего собирать."""
    while True:
        pattern = [rng.choice(MOVES) for _ in range(mc.BAR_BEATS)]
        if len(set(pattern)) > 1:
            return pattern


def deal_views(rng: random.Random, players: list[int]) -> dict[int, set[int]]:
    """Какие удары такта видит каждый. Солист видит всё; в группе каждый удар
    виден хотя бы одному и у каждого есть хотя бы один."""
    if len(players) <= 1:
        return {cid: set(range(mc.BAR_BEATS)) for cid in players}
    positions = list(range(mc.BAR_BEATS))
    rng.shuffle(positions)
    order = list(players)
    rng.shuffle(order)
    views: dict[int, set[int]] = {cid: set() for cid in players}
    for i in range(max(len(positions), len(order))):
        views[order[i % len(order)]].add(positions[i % len(positions)])
    return views


@dataclass
class BeatResult:
    stepped: bool
    wrong: list[int] = field(default_factory=list)
    fallen: list[int] = field(default_factory=list)
    new_pattern: bool = False


@dataclass
class Procession:
    players: list[int]
    rng: random.Random
    pattern: list[str] = field(default_factory=list)
    views: dict[int, set[int]] = field(default_factory=dict)
    beat: int = 0             # сыгранных ударов всего
    steps: int = 0            # шагов колонны
    lame: dict[int, int] = field(default_factory=dict)
    moves: dict[int, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.lame = {cid: 0 for cid in self.players}
        self._reshuffle()

    def _reshuffle(self) -> None:
        self.pattern = new_pattern(self.rng)
        self.views = deal_views(self.rng, self.players)

    @property
    def position(self) -> int:
        """Номер удара в такте, с нуля."""
        return self.beat % mc.BAR_BEATS

    @property
    def done(self) -> bool:
        return self.steps >= mc.STEPS_REQUIRED

    def rhythm_line(self, cid: int) -> str:
        seen = self.views.get(cid, set())
        parts = []
        for i, move in enumerate(self.pattern):
            word = MOVE_WORD[move] if i in seen else "?"
            parts.append(f"[{word}]" if i == self.position else word)
        return " · ".join(parts)

    def press(self, cid: int, move: str) -> bool:
        """Шаг выбран. False - уже выбирал в этот удар или не участник."""
        if cid not in self.lame or cid in self.moves or move not in MOVES:
            return False
        self.moves[cid] = move
        return True

    @property
    def ready(self) -> bool:
        return all(cid in self.moves for cid in self.players)

    def resolve(self) -> BeatResult:
        expected = self.pattern[self.position]
        wrong = [cid for cid in self.players if self.moves.get(cid) != expected]
        result = BeatResult(stepped=not wrong, wrong=wrong)
        if not wrong:
            self.steps += 1
        for cid in wrong:
            self.lame[cid] += 1
            if self.lame[cid] >= mc.LAME_LIMIT:
                self.lame[cid] = 0
                result.fallen.append(cid)
                self.steps = max(0, self.steps - mc.LAG_STEPS_LOST)
        self.moves = {}
        self.beat += 1
        if self.beat % mc.PATTERN_EVERY == 0 and not self.done:
            self._reshuffle()
            result.new_pattern = True
        return result
