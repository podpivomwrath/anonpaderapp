"""Гигиена текстов: всё, что видит игрок, - контент (JSON) и строки в коде бота.

Ловит механические ошибки, которые незаметны при чтении кода: длинное тире
(в игре только дефис), двойной пробел, латинскую букву внутри русского
слова, просочившееся «None». Докстринги и комментарии не проверяются -
их игрок не видит.
"""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CYR = re.compile(r"[А-Яа-яЁё]")

CHECKS = {
    "длинное тире": re.compile(r"—|–"),
    "двойной пробел": re.compile(r"\S  +\S"),
    "латиница внутри русского слова": re.compile(r"[А-Яа-яЁё][A-Za-z]|[A-Za-z][А-Яа-яЁё]"),
    "None в тексте": re.compile(r"\bNone\b|\bundefined\b"),
}
#: Шаблоны регулярных выражений - не текст для игрока.
_REGEX_LIKE = re.compile(r"\[A-Za-z|\^\[")


def _content_strings():
    for path in sorted((ROOT / "content").rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        stack = [(data, path.relative_to(ROOT).as_posix())]
        while stack:
            node, where = stack.pop()
            if isinstance(node, dict):
                stack += [(v, f"{where}.{k}") for k, v in node.items() if not k.startswith("_")]
            elif isinstance(node, list):
                stack += [(v, f"{where}[{i}]") for i, v in enumerate(node)]
            elif isinstance(node, str) and CYR.search(node):
                yield where, node


def _code_strings():
    for base in ("bot", "services", "game"):
        for path in sorted((ROOT / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            skip = {
                id(node.value) for node in ast.walk(tree)
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            }
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in skip and CYR.search(node.value)
                    and not _REGEX_LIKE.search(node.value)
                ):
                    yield f"{path.relative_to(ROOT).as_posix()}:{node.lineno}", node.value


ALL = list(_content_strings()) + list(_code_strings())


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_player_texts_are_clean(check: str) -> None:
    rx = CHECKS[check]
    bad = [f"{where}: {text[:80]!r}" for where, text in ALL if rx.search(text)]
    assert not bad, f"{check}:\n" + "\n".join(bad[:20])


def test_loot_and_victory_lines_never_name_a_creature() -> None:
    """Добыча приходит и с боя, и с этапа рейда, и из события - «тварь» в
    этих строках врала (награда за разгаданную загадку «осыпалась с твари»)."""
    from services import trophy_service

    for source in ("mob", "world_boss", "event"):
        line = trophy_service.format_drop_line({"ash_dust": 1}, source=source)
        assert "твар" not in line.lower()
    for rel in ("bot/handlers/combat.py", "bot/handlers/group_combat.py", "services/item_service.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "Тварь оседает" not in text and "С твари" not in text, rel
