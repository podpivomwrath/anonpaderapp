"""Иконка по id — разрешённое исключение, но не дыра (патч 90).

В `tests/test_no_raw_ids_in_text.py` есть правило: сырой id не показывают
игроку, для этого существуют названия. Эмблема подкласса в шапке мини-аппа
ищется как раз по id (`subclass:dark_mystic` — имя файла в itemIcons.js), и
названием его не заменить: названия переводятся и содержат пробелы.

Поэтому исключение сделано, но узкое: ключ по id разрешён только вместе с
человеческим названием в alt. Иначе скринридер и не загрузившаяся картинка
снова покажут игроку «dark_mystic» — ровно то, ради чего правило и вводили.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _jsx_files() -> list[Path]:
    return sorted((ROOT / "miniapp" / "src").rglob("*.jsx"))


KEY_FROM_ID = re.compile(r"icon=\{`\w+:\$\{")
#: Человеческое название - это `_title`, `.name` или просто написанный текст.
#: Сужать до одного `_title` нельзя: в мастерской давно и правильно стоят и
#: `alt={group.name}`, и `alt="Инструмент"` - тест ругался бы на здоровый код.
READABLE_ALT = re.compile(r"""alt=("[^"]+"|\{[^}]*(_title|\.name\b|['"]))""")


def test_icon_key_built_from_an_id_carries_a_readable_alt() -> None:
    offenders: list[str] = []
    for path in _jsx_files():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<ItemIcon\b[^>]*?/>", text, re.DOTALL):
            tag = match.group(0)
            if not KEY_FROM_ID.search(tag):
                continue  # ключ не собирается из id — проверять нечего
            if not READABLE_ALT.search(tag):
                offenders.append(f"{path.name}: {' '.join(tag.split())[:110]}")
    assert not offenders, "иконка по id без названия в alt:\n" + "\n".join(offenders)


def test_the_check_actually_finds_such_icons() -> None:
    """Страховка от молча-зелёного теста: если разметку перепишут и тег
    перестанет находиться, проверка выше останется зелёной навсегда."""
    found = [
        path.name
        for path in _jsx_files()
        for tag in re.findall(r"<ItemIcon\b[^>]*?/>", path.read_text(encoding="utf-8"), re.DOTALL)
        if KEY_FROM_ID.search(tag)
    ]
    assert found, "в мини-аппе не нашлось ни одной иконки с ключом по id"
