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


def test_game_voice_is_vy_but_npc_may_say_ty() -> None:
    """2026-11-13: отказы «Сначала очнись» жили в 11 местах на «ты» после
    перехода игры на «вы». Реплика персонажа («- ...») правилом не трогается."""
    ids = {r.id for r, *_ in text_slop.check_text("☠ Сначала очнись.")}
    assert "ty_system" in ids
    assert not text_slop.check_text("- Сначала закончи с этим, потом поговорим.", hard_only=True)
    assert not text_slop.check_text("☠ Вы ещё не очнулись.", hard_only=True)
    assert not text_slop.check_text("Нажми на кнопку.", where="patchnotes/2026-10-24-x.txt", hard_only=True)


def test_broadcast_blocks_slop_and_passes_clean_text() -> None:
    import broadcast

    hard, soft = broadcast.check("Патч — новая кнопка.")
    assert hard and broadcast.blocked(hard, soft, force=True)
    hard, soft = broadcast.check("Где-то вдали что-то шепчет.")
    assert not hard and soft
    assert broadcast.blocked(hard, soft, force=False) and not broadcast.blocked(hard, soft, force=True)
    hard, soft = broadcast.check("🔧 Патч: у Хранителя Списков появилась кнопка «Отказаться от пути».")
    assert not hard and not soft and not broadcast.blocked(hard, soft, force=False)


def test_text_files_outside_repo_are_scanned(tmp_path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("Что-то случилось...", encoding="utf-8")
    ids = {r.id for r, _p, _l, _f in text_slop.scan([str(note)])}
    assert {"someone", "ellipsis"} <= ids
