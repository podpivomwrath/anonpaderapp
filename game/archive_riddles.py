"""Второй этап «Безликого архива»: фраза из загадок. Чистая логика без VK.

Выпадает фраза на столько слов, сколько игроков (солисту -
SOLO_PHRASE_WORDS). Каждому - загадка, ответ на которую - его слово, и
номер этого слова во фразе. Лидер собирает ответы и вводит фразу целиком.
Связки фразы («и», «это», «хранит») лидер видит в шаблоне; при сверке они
не обязательны - важны слова-ответы и их порядок.
"""

import json
import random
from dataclasses import dataclass

from game.content_loader import CONTENT_DIR
from game.economy import raid_archive_config as ac
from game.world.scene_events import normalize_answer

_data: dict | None = None


def data() -> dict:
    global _data
    if _data is None:
        _data = json.loads((CONTENT_DIR / "raids" / "archive_riddles.json").read_text(encoding="utf-8"))
    return _data


@dataclass
class Assignment:
    """Загадка одного слова."""

    position: int          # номер слова во фразе, с 1
    word: str
    question: str
    answers: list[str]


@dataclass
class Phrase:
    template: str
    words: list[str]
    assignments: list[Assignment]

    @property
    def size(self) -> int:
        return len(self.words)

    def masked(self) -> str:
        """Шаблон для лидера: «_1_ и _2_»."""
        text = self.template
        for i in range(1, self.size + 1):
            text = text.replace("{" + str(i) + "}", f"[{i}]")
        return text

    def full(self) -> str:
        text = self.template
        for i, word in enumerate(self.words, start=1):
            text = text.replace("{" + str(i) + "}", word)
        return text


def deal(rng: random.Random, players: int) -> Phrase:
    size = players if players > 1 else ac.SOLO_PHRASE_WORDS
    size = max(2, min(size, 5))
    pick = rng.choice(data()["phrases"][str(size)])
    words = data()["words"]
    assignments = [
        Assignment(position=i, word=w, question=rng.choice(words[w]["riddles"]), answers=words[w]["answers"])
        for i, w in enumerate(pick["words"], start=1)
    ]
    return Phrase(template=pick["template"], words=list(pick["words"]), assignments=assignments)


def answer_is(text: str, assignment: Assignment) -> bool:
    given = set(normalize_answer(text).split())
    return any(normalize_answer(a) in given for a in assignment.answers)


def phrase_is(text: str, phrase: Phrase) -> bool:
    """Фраза верна, если слова-ответы стоят в нужном порядке. Связки из
    шаблона можно писать, можно опустить: «тень и свеча» = «тень свеча»."""
    given = [w for w in normalize_answer(text).split() if w not in _connectors(phrase)]
    expected = [normalize_answer(w) for w in phrase.words]
    return given == expected


def _connectors(phrase: Phrase) -> set[str]:
    text = phrase.template
    for i in range(1, phrase.size + 1):
        text = text.replace("{" + str(i) + "}", " ")
    return set(normalize_answer(text).split())
