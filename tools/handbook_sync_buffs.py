"""Описания микробаффов в путеводителе = описания из игры (2026-10-23).

В главе «Навыки и формулы» (miniapp/src/handbook.json) баффы перечислены
строками «<b>Название</b> - описание». Описание в игре собирает
game/economy/buff_descriptions.py из живых чисел; путеводитель хранит копию.
Скрипт переписывает копии по текущему коду; tests/test_handbook.py падает,
если их забыли обновить.

    python tools/handbook_sync_buffs.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HANDBOOK = ROOT / "miniapp" / "src" / "handbook.json"
LINE = re.compile(r"^<b>(?P<name>[^<]+)</b> - (?P<text>.*)$")


def current_descriptions() -> dict[str, list[str]]:
    """Название баффа -> описания (у пути без подкласса имена бывают общими)."""
    from game.content_loader import load_content
    from game.economy import buff_descriptions

    out: dict[str, list[str]] = {}
    for buff in load_content().buffs.values():
        text = buff_descriptions.describe(buff)
        if text:
            out.setdefault(buff.name, []).append(text)
    return out


def _walk(blocks, fn) -> None:
    for b in blocks:
        if b.get("t") in ("ul", "ol"):
            b["items"] = [fn(item) for item in b["items"]]
        if b.get("t") == "details":
            _walk(b["blocks"], fn)


def sync(data: dict, descriptions: dict[str, list[str]]) -> list[str]:
    """Обновляет data на месте; возвращает изменённые названия."""
    changed: list[str] = []

    def fix(item: str) -> str:
        m = LINE.match(item)
        if not m:
            return item
        variants = descriptions.get(m["name"])
        # Несколько баффов с одним именем - не угадываем, какой здесь.
        if not variants or len(variants) != 1 or variants[0] == m["text"]:
            return item
        changed.append(m["name"])
        return f"<b>{m['name']}</b> - {variants[0]}"

    for chapter in data["chapters"]:
        _walk(chapter["blocks"], fix)
    return changed


if __name__ == "__main__":
    data = json.loads(HANDBOOK.read_text(encoding="utf-8"))
    changed = sync(data, current_descriptions())
    HANDBOOK.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"обновлено: {len(changed)}", ", ".join(changed))
