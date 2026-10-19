"""Жёсткие правила игрового текста (.claude/skills/game-text/SKILL.md):
нарушений в игре быть не должно совсем. Мягкие приметы - tools/text_slop.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import text_slop  # noqa: E402


def test_no_hard_slop_in_game_texts() -> None:
    hits = text_slop.scan(hard_only=True)
    assert not hits, "\n".join(f"{p}:{line} [{r.id}] {frag}" for r, p, line, frag in hits[:20])


def test_detector_catches_typical_slop() -> None:
    sample = "Пепел тут не грязь, а почва. Где-то вдали что-то шепчет, словно помнит тебя..."
    found = {r.id for r in text_slop.RULES if r.pattern.search(sample)}
    assert {"not_but", "someone", "silence", "simile", "ellipsis"} <= found
