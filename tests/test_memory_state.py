"""Каждое хранилище бота в памяти записано в bot/memory_state.py с ответом
«кто его снимает» (2026-10-21: строка взноса гильдии ждала «следующей победы»
и доезжала до боя в пути на маунте)."""

import re
from pathlib import Path

from bot.memory_state import STATE

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^(_[a-z_0-9]+)(: [^=]+)? = (\{\}|set\(\)|dict\(\)|defaultdict\(|deque\(|OrderedDict\()")


def _found() -> set[str]:
    out = set()
    for path in (ROOT / "bot").rglob("*.py"):
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for line in path.read_text(encoding="utf-8").splitlines():
            match = PATTERN.match(line)
            if match:
                out.add(f"{module}.{match.group(1)}")
    return out


def test_every_in_memory_store_says_who_clears_it() -> None:
    found = _found()
    missing = sorted(found - STATE.keys())
    stale = sorted(STATE.keys() - found)
    assert not missing, f"новое хранилище в памяти - впиши в bot/memory_state.py, кто его снимает: {missing}"
    assert not stale, f"хранилища больше нет - убери из bot/memory_state.py: {stale}"
    assert all(len(text) > 5 for text in STATE.values())
