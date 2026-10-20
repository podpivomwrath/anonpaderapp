"""Головоломки первого этапа «Безликого архива»: чистая логика без VK.

Каждая головоломка - поле кнопок (cells) и нажатие (press). Бот рисует
cells клавиатурой, payload кнопки несёт value, обратно приходит press(value).
Раскладки случайные, но всегда решаемые: генерируются ходами от решённого
состояния, а не случайной расстановкой.

У каждого игрока группы своя головоломка - пять видов на пятерых.
"""

import itertools
import random

from game.economy import raid_archive_config as ac

TTT, PAIRS, PAGES, CANDLES, RUNES = "ttt", "pairs", "pages", "candles", "runes"
KINDS = (TTT, PAIRS, PAGES, CANDLES, RUNES)

Cell = tuple[str, str]  # (подпись кнопки, value)


class Puzzle:
    kind = ""
    title = ""
    rules = ""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.solved = False

    def cells(self) -> list[list[Cell]]:
        raise NotImplementedError

    def status(self) -> str:
        return ""

    def press(self, value: str) -> str:
        """Ход игрока. Возвращает строку о том, что случилось (может быть пустой)."""
        raise NotImplementedError


# --- Крестики-нолики ---------------------------------------------------------------

_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


def _winner(board: list[str]) -> str | None:
    for a, b, c in _LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


class TicTacToe(Puzzle):
    kind = TTT
    title = "❌⭕ Крестики-нолики"
    rules = f"Ты - крестики, ходишь первым. Нужно {ac.TTT_WINS} победы над Архивариусом. Ничья и поражение счёт не сбрасывают."

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.board = [""] * 9
        self.wins = 0

    def cells(self) -> list[list[Cell]]:
        marks = {"": "·", "X": "❌", "O": "⭕"}
        return [[(marks[self.board[r * 3 + c]], str(r * 3 + c)) for c in range(3)] for r in range(3)]

    def status(self) -> str:
        return f"Побед: {self.wins}/{ac.TTT_WINS}"

    def press(self, value: str) -> str:
        if not value.isdigit() or not 0 <= int(value) < 9 or self.board[int(value)] or self.solved:
            return ""
        self.board[int(value)] = "X"
        if _winner(self.board) == "X":
            self.wins += 1
            self.board = [""] * 9
            if self.wins >= ac.TTT_WINS:
                self.solved = True
                return "Третья победа. Архивариус молча стирает доску."
            return "Победа! Доска стирается."
        if all(self.board):
            self.board = [""] * 9
            return "Ничья. Новая доска."
        self.board[self._reply()] = "O"
        if _winner(self.board) == "O":
            self.board = [""] * 9
            return "Архивариус собрал линию. Новая доска."
        if all(self.board):
            self.board = [""] * 9
            return "Ничья. Новая доска."
        return ""

    def _reply(self) -> int:
        free = [i for i in range(9) if not self.board[i]]
        for mark in ("O", "X"):
            for i in free:
                trial = list(self.board)
                trial[i] = mark
                if _winner(trial) == mark:
                    # Свою линию он замыкает всегда, твою - не всегда замечает.
                    if mark == "O" or self.rng.random() < ac.TTT_BLOCK_CHANCE:
                        return i
        if not self.board[4] and self.rng.random() < 0.5:
            return 4
        return self.rng.choice(free)


# --- Пары --------------------------------------------------------------------------

_SYMBOLS = ("📕", "🕯", "🗝", "🪶", "⏳", "👁")


class Pairs(Puzzle):
    kind = PAIRS
    title = "🃏 Пары"
    rules = "Под плитками шесть пар знаков. Открывай по две: совпали - остаются, нет - закроются."

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.tiles = list(_SYMBOLS) * 2
        rng.shuffle(self.tiles)
        self.matched: set[int] = set()
        self.first: int | None = None
        self.shown: tuple[int, int] | None = None  # несовпавшая пара, видна до следующего нажатия

    def cells(self) -> list[list[Cell]]:
        visible = set(self.matched)
        if self.first is not None:
            visible.add(self.first)
        if self.shown:
            visible.update(self.shown)
        return [
            [(self.tiles[i] if i in visible else "❔", str(i)) for i in range(r * 3, r * 3 + 3)]
            for r in range(4)
        ]

    def status(self) -> str:
        return f"Пар найдено: {len(self.matched) // 2}/{len(_SYMBOLS)}"

    def press(self, value: str) -> str:
        if not value.isdigit() or self.solved:
            return ""
        i = int(value)
        if not 0 <= i < len(self.tiles) or i in self.matched or i == self.first:
            return ""
        self.shown = None
        if self.first is None:
            self.first = i
            return ""
        a, self.first = self.first, None
        if self.tiles[a] == self.tiles[i]:
            self.matched.update((a, i))
            if len(self.matched) == len(self.tiles):
                self.solved = True
                return "Последняя пара сходится."
            return "Пара!"
        self.shown = (a, i)
        return "Не пара."


def _neighbors(i: int) -> list[int]:
    """Соседи крестом на поле 3×3 (свечи)."""
    r, c = divmod(i, 3)
    out = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < 3 and 0 <= nc < 3:
            out.append(nr * 3 + nc)
    return out


# --- Проклятые страницы (мини-сапёр, 2026-10-20 вместо пятнашек) -------------------
# Пятнашки собирались за 20-40 ходов, и клавиатура VK на каждом ходу делала
# игру вязкой. Здесь 6-10 нажатий, и каждое что-то открывает.

PAGES_ROWS, PAGES_COLS, PAGES_CURSED = 4, 3, 2
#: Сколько чистых страниц должно остаться закрытыми после первого нажатия.
PAGES_MIN_LEFT = 3
_PAGE_CLOSED = "📄"
_PAGE_NUMBERS = ("▫️", "1", "2", "3", "4", "5", "6", "7", "8")


def _around(i: int) -> list[int]:
    """Соседи по всем 8 направлениям на поле страниц."""
    r, c = divmod(i, PAGES_COLS)
    return [
        nr * PAGES_COLS + nc
        for nr in range(r - 1, r + 2) for nc in range(c - 1, c + 2)
        if (nr, nc) != (r, c) and 0 <= nr < PAGES_ROWS and 0 <= nc < PAGES_COLS
    ]


def _counts(cursed: set[int]) -> list[int]:
    return [sum(1 for n in _around(i) if n in cursed) for i in range(PAGES_ROWS * PAGES_COLS)]


def _open_from(i: int, counts: list[int], cursed: set[int], opened: set[int]) -> None:
    """Открыть страницу; у нуля - сразу и всех соседей, как в сапёре."""
    stack = [i]
    while stack:
        j = stack.pop()
        if j in opened or j in cursed:
            continue
        opened.add(j)
        if counts[j] == 0:
            stack.extend(_around(j))


def solvable_without_guessing(first: int, cursed: set[int]) -> bool:
    """Решается ли поле одной логикой: перебор всех раскладок проклятий,
    согласных с открытыми числами, и открытие страниц, чистых во ВСЕХ из них."""
    size = PAGES_ROWS * PAGES_COLS
    counts = _counts(cursed)
    opened: set[int] = set()
    _open_from(first, counts, cursed, opened)
    while len(opened) < size - len(cursed):
        closed = [i for i in range(size) if i not in opened]
        layouts = [
            set(combo) for combo in itertools.combinations(closed, len(cursed))
            if all(_counts(set(combo))[i] == counts[i] for i in opened)
        ]
        safe = [i for i in closed if all(i not in lay for lay in layouts)]
        if not safe:
            return False
        for i in safe:
            _open_from(i, counts, cursed, opened)
    return True


class Pages(Puzzle):
    kind = PAGES
    title = "📜 Проклятые страницы"
    rules = (
        f"Под {PAGES_CURSED} страницами проклятие. Открытая страница показывает число проклятых "
        "соседей, считая наискосок. Первая страница всегда чистая. Открой все чистые. Тронешь "
        "проклятую - страницы перемешаются, начнёшь сначала."
    )

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self._reset()

    def _reset(self) -> None:
        # Проклятия раскладываются после первого нажатия: первая страница всегда чистая.
        self.cursed: set[int] = set()
        self.counts: list[int] = []
        self.opened: set[int] = set()

    def _deal(self, first: int) -> None:
        size = PAGES_ROWS * PAGES_COLS
        keep_clear = {first}
        free = [i for i in range(size) if i not in keep_clear]
        # Все раскладки, решаемые логикой; из них - те, где после первого
        # нажатия остаётся больше всего работы: иначе это не головоломка, а
        # один клик, открывающий всё поле.
        best: list[set[int]] = []
        best_left = -1
        for combo in itertools.combinations(free, PAGES_CURSED):
            cursed = set(combo)
            if not solvable_without_guessing(first, cursed):
                continue
            opened: set[int] = set()
            _open_from(first, _counts(cursed), cursed, opened)
            left = min(size - PAGES_CURSED - len(opened), PAGES_MIN_LEFT)
            if left > best_left:
                best, best_left = [cursed], left
            elif left == best_left:
                best.append(cursed)
        cursed = self.rng.choice(best) if best else set(self.rng.sample(free, PAGES_CURSED))
        self.cursed = cursed
        self.counts = _counts(cursed)

    def cells(self) -> list[list[Cell]]:
        return [
            [
                (_PAGE_NUMBERS[self.counts[i]] if i in self.opened else _PAGE_CLOSED, str(i))
                for i in range(r * PAGES_COLS, (r + 1) * PAGES_COLS)
            ]
            for r in range(PAGES_ROWS)
        ]

    def status(self) -> str:
        left = PAGES_ROWS * PAGES_COLS - PAGES_CURSED - len(self.opened)
        return f"Чистых страниц осталось: {left}"

    def press(self, value: str) -> str:
        if not value.isdigit() or self.solved:
            return ""
        i = int(value)
        if not 0 <= i < PAGES_ROWS * PAGES_COLS or i in self.opened:
            return ""
        if not self.cursed:
            self._deal(i)
        if i in self.cursed:
            self._reset()
            return "Страница чернеет у тебя в руках. Листы взлетают и ложатся заново, все закрытые."
        _open_from(i, self.counts, self.cursed, self.opened)
        if len(self.opened) == PAGES_ROWS * PAGES_COLS - PAGES_CURSED:
            self.solved = True
            return "Последняя чистая страница открыта. Проклятые сворачиваются в трубку."
        return ""


# --- Свечи ------------------------------------------------------------------------


class Candles(Puzzle):
    kind = CANDLES
    title = "🕯 Свечи"
    rules = "Погаси все свечи. Нажатие переключает свечу и её соседей крестом: сверху, снизу, слева и справа."

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.lit = [False] * 9
        # Зажигаем теми же нажатиями, которыми потом гасить, - решение есть всегда.
        while not any(self.lit):
            for i in rng.sample(range(9), rng.randint(3, 5)):
                self._toggle(i)
        self.moves = 0

    def _toggle(self, i: int) -> None:
        for j in (i, *_neighbors(i)):
            self.lit[j] = not self.lit[j]

    def cells(self) -> list[list[Cell]]:
        return [[("🕯" if self.lit[r * 3 + c] else "▪️", str(r * 3 + c)) for c in range(3)] for r in range(3)]

    def status(self) -> str:
        return f"Горит: {sum(self.lit)}/9"

    def press(self, value: str) -> str:
        if not value.isdigit() or self.solved or not 0 <= int(value) < 9:
            return ""
        self._toggle(int(value))
        self.moves += 1
        if not any(self.lit):
            self.solved = True
            return "Последний огонёк гаснет, и в темноте щёлкает замок."
        return ""


# --- Руны замка -------------------------------------------------------------------

_RUNES = ("ᚠ", "ᚢ", "ᚦ", "ᚨ", "ᚱ", "ᚲ")
#: Пустая скобка (2026-10-18): широкие пробелы, чтобы по ширине была как со значком.
_EMPTY = "  "
ERASE = "erase"


class Runes(Puzzle):
    kind = RUNES
    title = "🔐 Руны замка"
    rules = (
        f"Замок загадал {ac.RUNE_CODE_LEN} разные руны. Набирай по одной. После каждой попытки "
        f"у каждой руны своя скобка: [✅] - руна на месте, [🔸] - руна есть, но не здесь, "
        f"[{_EMPTY}] - такой руны нет. Попыток {ac.RUNE_ATTEMPTS}, потом код меняется."
    )

    def __init__(self, rng: random.Random) -> None:
        super().__init__(rng)
        self.history: list[str] = []
        self._new_code()

    def _new_code(self) -> None:
        self.code = self.rng.sample(_RUNES, ac.RUNE_CODE_LEN)
        self.typed: list[str] = []
        self.attempts = ac.RUNE_ATTEMPTS
        self.history = []

    def cells(self) -> list[list[Cell]]:
        return [
            [(r, r) for r in _RUNES[:3]],
            [(r, r) for r in _RUNES[3:]],
            [("⌫ Стереть", ERASE)],
        ]

    def status(self) -> str:
        lines = list(self.history)
        typed = " ".join(self.typed) or "-"
        lines.append(f"Набрано: {typed} · попыток: {self.attempts}")
        return "\n".join(lines)

    @staticmethod
    def score(code: list[str], guess: list[str]) -> tuple[int, int]:
        exact = sum(1 for a, b in zip(code, guess, strict=True) if a == b)
        present = sum(1 for g in guess if g in code) - exact
        return exact, present

    @staticmethod
    def marks(code: list[str], guess: list[str]) -> str:
        """Значок у каждой руны, по местам (2026-10-18, решение владельца):
        раньше был только счёт ✅🔸🔸, и игроки читали его как места."""
        return " ".join(
            f"[{'✅' if g == c else '🔸' if g in code else _EMPTY}]"
            for g, c in zip(guess, code, strict=True)
        )

    def press(self, value: str) -> str:
        if self.solved:
            return ""
        if value == ERASE:
            self.typed = self.typed[:-1]
            return ""
        if value not in _RUNES or value in self.typed:
            return ""
        self.typed.append(value)
        if len(self.typed) < ac.RUNE_CODE_LEN:
            return ""
        exact, present = self.score(self.code, self.typed)
        self.history.append(f"{' '.join(self.typed)}  {self.marks(self.code, self.typed)}")
        self.typed = []
        self.attempts -= 1
        if exact == ac.RUNE_CODE_LEN:
            self.solved = True
            return "Замок узнаёт руны и открывается."
        if self.attempts <= 0:
            self._new_code()
            return "Попытки кончились. Замок перещёлкивается - код теперь другой."
        return ""


_CLASSES = {TTT: TicTacToe, PAIRS: Pairs, PAGES: Pages, CANDLES: Candles, RUNES: Runes}


def deal(rng: random.Random, players: int) -> list[Puzzle]:
    """По головоломке на игрока, без повторов внутри группы."""
    kinds = list(KINDS)
    rng.shuffle(kinds)
    return [_CLASSES[kinds[i % len(kinds)]](rng) for i in range(players)]
