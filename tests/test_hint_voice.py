"""Озвучка подсказок (2026-10-22): у каждого шага с voice есть файл, и
каждый файл озвучки к чему-то привязан - иначе он молча лежит в сборке."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "miniapp" / "src"


DISABLED = {"hint_exchange_1", "hint_exchange_2", "hint_exchange_3"}


def test_every_voice_key_has_a_file_and_back() -> None:
    keys = set()
    for name in ("components/tabHints.js", "components/Tour.jsx"):
        keys |= set(re.findall(r"voice: '([a-z0-9_]+)'", (SRC / name).read_text(encoding="utf-8")))
    # Отключённые, но сохранённые записи: биржа ушла в «Рынок» (2026-10-23).
    files = {p.stem for p in (SRC / "assets" / "voice").glob("*.mp3")} - DISABLED
    assert keys and keys == files, f"без файла: {sorted(keys - files)}, без шага: {sorted(files - keys)}"
