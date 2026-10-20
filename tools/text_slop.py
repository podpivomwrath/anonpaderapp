"""Поиск «нейрослопа» в игровых текстах.

Запуск:  python tools/text_slop.py [--top N] [--rule ID] [путь ...]

Берёт строковые литералы из bot/*.py, game/**/*.py и строки из content/**/*.json,
ищет приметы машинного текста (правила - .claude/skills/game-text/SKILL.md) и
печатает находки по правилам. Жёсткие правила (HARD) проверяет тест
tests/test_text_slop.py - их в игре быть не должно совсем.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CYR = re.compile(r"[а-яё]", re.I)


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    pattern: re.Pattern
    hard: bool = False


def _r(expr: str) -> re.Pattern:
    return re.compile(expr, re.I)


RULES = (
    Rule("dash", "длинное тире (в игре только дефис)", _r(r"[—–]"), hard=True),
    Rule("not_but", "«не X, а Y» / «не X - Y»", _r(r"\bне\s+[^,.!?\n]{1,40},\s+а\s+")),
    Rule("not_x_dot", "«Не X. Y.» - отрицание ради контраста", _r(r"(?:^|[.!?]\s+)Не\s+\w+(?:\s+\w+)?\.\s+[А-ЯЁ]")),
    Rule("simile", "сравнения «словно / будто / как будто»", _r(r"\b(словно|будто|точно\s+(?=\w+\s))")),
    Rule("someone", "«кто-то / что-то / где-то» - туманная значительность", _r(r"\b(кто|что|где|откуда|когда)-то\b")),
    Rule("silence", "тишина, шёпот, эхо, пустота, вечность", _r(r"\b(тишин\w*|шёпот\w*|шепч\w*|эхо\b|пустот\w*|вечност\w*|бездн\w*)")),
    Rule("smell", "«пахнет / запах / привкус» - чек-лист ощущений", _r(r"\b(пахн\w*|запах\w*|привкус\w*|тянет\s+\w*запах)")),
    Rule("again", "«снова и снова», «раз за разом», «всё ещё»", _r(r"(снова,?\s+и\s+снова|раз\s+за\s+разом|всё\s+ещё)")),
    Rule("feel", "«ты чувствуешь / ощущаешь»", _r(r"\b(чувству\w+|ощуща\w+)")),
    Rule("ellipsis", "многоточие", _r(r"\.\.\.|…")),
    Rule("seems", "«кажется / как будто бы / почти»", _r(r"\b(кажется|почти\s+(?:не|как))")),
    Rule("remembers", "оживление вещей: «камень помнит», «дорога знает»", _r(r"\b(помн\w+|зна\w+)\s+(?:тебя|вас|всё|каждого)")),
)

#: Короткая «ударная» фраза в конце абзаца: 1-3 слова и точка.
PUNCH = re.compile(r"(?:^|[.!?]\s+)((?:[А-ЯЁ][^\s.!?]*)(?:\s+[^\s.!?]+){0,2})\.\s*$", re.M)


def _literals(path: Path) -> list[tuple[int, str]]:
    if path.suffix in (".txt", ".md"):
        # Патчноуты и рассылки (tools/broadcast.py): весь файл - один текст.
        return [(1, path.read_text(encoding="utf-8"))]
    if path.suffix == ".json":
        out: list[tuple[int, str]] = []

        def walk(node) -> None:
            if isinstance(node, str):
                out.append((0, node))
            elif isinstance(node, dict):
                for key, value in node.items():
                    if not str(key).startswith("_"):
                        walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, UnicodeDecodeError):
            return []
        return out
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            out.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
            out.append((node.lineno, text))
    return out


def game_files(paths: list[str] | None = None) -> list[Path]:
    if paths:
        # Абсолютный путь (файл вне репозитория) Path склеит как есть.
        return [ROOT / p for p in paths]
    files = sorted((ROOT / "bot").rglob("*.py")) + sorted((ROOT / "game").rglob("*.py"))
    files += sorted((ROOT / "content").rglob("*.json"))
    files += sorted((ROOT / "patchnotes").glob("*.txt"))
    return [f for f in files if "__pycache__" not in f.parts]


def _shown(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def check_text(text: str, hard_only: bool = False, where: str = "текст", lineno: int = 1):
    """[(rule, где, строка, фрагмент)] для одного текста - то же, что scan."""
    hits = []
    if not CYR.search(text):
        return hits
    for rule in RULES:
        if hard_only and not rule.hard:
            continue
        for m in rule.pattern.finditer(text):
            start = max(0, m.start() - 30)
            frag = text[start:m.end() + 30].replace("\n", " ")
            hits.append((rule, where, lineno, frag))
    if not hard_only and len(text) > 120:
        for m in PUNCH.finditer(text):
            hits.append((_PUNCH_RULE, where, lineno, m.group(1)))
    return hits


def scan(paths: list[str] | None = None, hard_only: bool = False):
    """[(rule, файл, строка, фрагмент)]"""
    hits = []
    for path in game_files(paths):
        for lineno, text in _literals(path):
            hits += check_text(text, hard_only, _shown(path), lineno)
    return hits


_PUNCH_RULE = Rule("punch", "ударная фраза в 1-3 слова в конце абзаца", re.compile(""))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--rule")
    args = parser.parse_args()
    by_rule = defaultdict(list)
    for rule, path, line, frag in scan(args.paths or None):
        by_rule[rule.id].append((rule, path, line, frag))
    for rule_id, items in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
        if args.rule and rule_id != args.rule:
            continue
        rule = items[0][0]
        print(f"\n## {rule.title} [{rule_id}] - {len(items)}")
        for _, path, line, frag in items[: args.top if not args.rule else None]:
            print(f"  {path}:{line}  …{frag}…")


if __name__ == "__main__":
    main()
