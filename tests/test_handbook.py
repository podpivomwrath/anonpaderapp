"""Путеводитель в мини-аппе (2026-10-23): handbook.json и ссылки на разделы.

Ссылки в handbookLinks.js ведут на главу по id и подраздел по тексту
заголовка. Переименовали заголовок в handbook.json - ссылка молча вела бы в
никуда; этот тест ловит.
"""

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "miniapp" / "src"
DATA = json.loads((SRC / "handbook.json").read_text(encoding="utf-8"))
LINKS = (SRC / "handbookLinks.js").read_text(encoding="utf-8")
TERM = re.compile(r"\[`[^`]*`, '(\w+)', (null|'[^']*')\]|\['[^']*', '(\w+)', (null|'[^']*')\]")


def _headings(blocks):
    for b in blocks:
        if b["t"] in ("h3", "h4"):
            yield b["text"]
        if b["t"] == "details":
            yield from _headings(b["blocks"])


def test_chapters_have_titles_and_blocks() -> None:
    assert len(DATA["chapters"]) >= 10
    ids = [c["id"] for c in DATA["chapters"]]
    assert len(ids) == len(set(ids))
    for c in DATA["chapters"]:
        assert c["title"] and c["no"] and c["blocks"], c["id"]


def test_link_targets_exist() -> None:
    chapters = {c["id"]: set(_headings(c["blocks"])) for c in DATA["chapters"]}
    targets = [(m[0] or m[2], m[1] or m[3]) for m in TERM.findall(LINKS)]
    assert len(targets) > 20
    for ch, sec in targets:
        assert ch in chapters, f"нет главы {ch}"
        if sec != "null":
            assert sec.strip("'") in chapters[ch], f"в главе {ch} нет подраздела {sec}"


def test_only_bold_markup_in_text() -> None:
    text = json.dumps(DATA, ensure_ascii=False)
    assert not re.search(r"<(?!/?b>)[a-z]", text), "в тексте только <b>"


def test_buff_descriptions_match_the_game() -> None:
    """Описания баффов в путеводителе - копия игровых; поменял бафф - запусти
    tools/handbook_sync_buffs.py."""
    import copy
    import sys

    sys.path.insert(0, str(SRC.parent.parent / "tools"))
    import handbook_sync_buffs as hs

    stale = hs.sync(copy.deepcopy(DATA), hs.current_descriptions())
    assert not stale, f"устарели в путеводителе: {stale} - python tools/handbook_sync_buffs.py"
