"""Вид записи журнала ресурсов влезает в колонку (2026-10-22).

Разбор уникалок писал вид «star_dust» в String(8): на Postgres запись
падала и откатывала весь разбор, а SQLite в тестах длину не проверяет -
ошибку увидели только игроки. Тест смотрит все явные resource_log.add в
коде и сверяет длину вида с колонкой.
"""

import re
from pathlib import Path

from models import ResourceLog

ROOT = Path(__file__).resolve().parent.parent
CALL = re.compile(r'resource_log\.add\([^,]+,[^,]+,\s*"([^"]+)"')


def test_every_kind_fits_the_column():
    limit = ResourceLog.__table__.c.kind.type.length
    found = {}
    for folder in ("services", "bot", "game"):
        for path in (ROOT / folder).rglob("*.py"):
            for kind in CALL.findall(path.read_text(encoding="utf-8")):
                found[kind] = path.name
    assert found, "не нашли ни одного resource_log.add - поменялся вызов?"
    too_long = {k: f for k, f in found.items() if len(k) > limit}
    assert not too_long, f"вид длиннее {limit} знаков: {too_long}"
