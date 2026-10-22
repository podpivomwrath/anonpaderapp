"""Озвучка подсказок (2026-10-22): у каждого шага с voice есть файл, и
каждый файл озвучки к чему-то привязан - иначе он молча лежит в сборке."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "miniapp" / "src"


def test_every_voice_key_has_a_file_and_back() -> None:
    keys = set()
    for name in ("components/tabHints.js", "components/Tour.jsx"):
        keys |= set(re.findall(r"voice: '([a-z0-9_]+)'", (SRC / name).read_text(encoding="utf-8")))
    files = {p.stem for p in (SRC / "assets" / "voice").glob("*.mp3")}
    assert keys and keys == files, f"без файла: {sorted(keys - files)}, без шага: {sorted(files - keys)}"
