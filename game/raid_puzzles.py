"""Головоломки первого этапа «Безликого архива»: чистая логика без VK.

Каждая головоломка - поле кнопок (cells) и нажатие (press). Бот рисует
cells клавиатурой, payload кнопки несёт value, обратно приходит press(value).
Раскладки случайные, но всегда решаемые: генерируются ходами от решённого
состояния, а не случайной расстановкой.

У каждого игрока группы своя головоломка - пять видов на пятерых.
"""

import random

from game.economy import raid_archive_config as ac

TTT, PAIRS, SLIDE, CANDLES, RUNES = "ttt", "pairs", "slide", "candles", "runes"
KINDS = (TTT, PAIRS, SLIDE, CANDLES, RUNES)

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


# --- Пятнашки 3×3 ------------------------------------------------------------------


def _neighbors(i: int) -> list[int]:
    r, c = divmod(i, 3)
    out = []
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < 3 and 0 <= nc < 3:
            out.append(nr * 3 + nc)
    return out


class Slide(Puzzle):
    kind = SLIDE
    title = "🔢 Пятнашки"
    rules = "Собери плитки по порядку 1-8, пустая клетка - в правом нижнем углу. Двигается плитка рядом с пустой."

    SOLVED = [1, 2, 3, 4, 5, 6, 7, 8, 0]

    def __init__(self, rng: random.Random, shuffle_moves: int = 40) -> None:
        super().__init__(rng)
        self.board = list(self.SOLVED)
        prev = None
        # Перемешивание ходами от решённого - раскладка всегда собираемая.
        while self.board == self.SOLVED:
            for _ in range(shuffle_moves):
                empty = self.board.index(0)
                options = [n for n in _neighbors(empty) if n != prev]
                pick = rng.choice(options)
                self.board[empty], self.board[pick] = self.board[pick], 0
                prev = empty
        self.moves = 0

    def cells(self) -> list[list[Cell]]:
        return [[(str(v) if v else "▫️", str(r * 3 + c)) for c, v in enumerate(self.board[r * 3:r * 3 + 3])]
                for r in range(3)]

    def status(self) -> str:
        return f"Ходов: {self.moves}"

    def press(self, value: str) -> str:
        if not value.isdigit() or self.solved:
            return ""
        i = int(value)
        empty = self.board.index(0)
        if i not in _neighbors(empty):
            return ""
        self.board[empty], self.board[i] = self.board[i], 0
        self.moves += 1
        if self.board == self.SOLVED:
            self.solved = True
            return "Плитки встают на места с сухим щелчком."
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
ERASE = "erase"


class Runes(Puzzle):
    kind = RUNES
    title = "🔐 Руны замка"
    rules = (
        f"Замок загадал {ac.RUNE_CODE_LEN} разные руны. Набирай по одной. После каждой попытки: "
        f"✅ - руна на месте, 🔸 - руна есть, но не там. Попыток {ac.RUNE_ATTEMPTS}, потом код меняется."
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
        self.history.append(f"{' '.join(self.typed)}  {'✅' * exact}{'🔸' * present}" or "пусто")
        self.typed = []
        self.attempts -= 1
        if exact == ac.RUNE_CODE_LEN:
            self.solved = True
            return "Замок узнаёт руны и открывается."
        if self.attempts <= 0:
            self._new_code()
            return "Попытки кончились. Замок перещёлкивается - код теперь другой."
        return ""


_CLASSES = {TTT: TicTacToe, PAIRS: Pairs, SLIDE: Slide, CANDLES: Candles, RUNES: Runes}


def deal(rng: random.Random, players: int) -> list[Puzzle]:
    """По головоломке на игрока, без повторов внутри группы."""
    kinds = list(KINDS)
    rng.shuffle(kinds)
    return [_CLASSES[kinds[i % len(kinds)]](rng) for i in range(players)]
