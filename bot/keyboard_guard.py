"""Проверка клавиатуры перед отправкой (2026-11-14).

VK отклоняет сообщение целиком, если клавиатура нарушает его лимиты, - и
игрок не получает вообще ничего (13.11 у Есты так дважды пропал ответ:
«buttons contain too much rows», а 05.11 - кнопка-ссылка в ряду из трёх).
Какой экран это был, по журналу уже не восстановить: вызов глотал ошибку.

Здесь - сеть для всех отправок (зовёт обёртка в bot/silent_guard.py):
клавиатура приводится к лимитам VK, сообщение уходит, а в журнал ошибок
пишутся подписи кнопок - по ним чинится сам экран. Правило игры (не больше
5 рядов на экран, bot/keyboards/layout.py) строже лимитов VK и проверяется
тестами отдельно; здесь только то, без чего VK не примет сообщение.
"""

from __future__ import annotations

import json

from loguru import logger

#: Лимиты VK: рядов у обычной клавиатуры и у встроенной, кнопок в ряду.
MAX_ROWS = 10
MAX_ROWS_INLINE = 6
MAX_IN_ROW = 5
#: Кнопки «во всю ширину»: VK пускает их только в ряд не длиннее двух.
WIDE_TYPES = {"open_link", "open_app", "vkpay", "location"}
WIDE_ROW_MAX = 2


def _kind(button: dict) -> str:
    return str((button.get("action") or {}).get("type", "text"))


def _label(button: dict) -> str:
    return str((button.get("action") or {}).get("label") or _kind(button))


def _fix_rows(rows: list[list[dict]], inline: bool) -> tuple[list[list[dict]], list[str]]:
    problems: list[str] = []
    out: list[list[dict]] = []
    for row in rows:
        if not row:
            continue
        limit = WIDE_ROW_MAX if any(_kind(b) in WIDE_TYPES for b in row) else MAX_IN_ROW
        if len(row) > limit:
            problems.append(f"в ряду {len(row)} кнопок при пределе {limit}")
            out.extend(row[i:i + limit] for i in range(0, len(row), limit))
        else:
            out.append(row)

    max_rows = MAX_ROWS_INLINE if inline else MAX_ROWS
    if len(out) > max_rows:
        problems.append(f"рядов {len(out)} при пределе {max_rows}")
    while len(out) > max_rows:
        # Сливаем два соседних коротких ряда обычных кнопок - самую короткую пару.
        best = None
        for i in range(len(out) - 1):
            pair = out[i] + out[i + 1]
            fits = len(pair) <= MAX_IN_ROW - 1 and not any(_kind(b) in WIDE_TYPES for b in pair)
            if fits and (best is None or len(pair) < len(out[best] + out[best + 1])):
                best = i
        if best is not None:
            out[best:best + 2] = [out[best] + out[best + 1]]
            continue
        # Слить нечего - убираем предпоследний ряд (последний обычно «Назад»
        # или мини-апп).
        out.pop(-2)
    return out, problems


def checked(keyboard):
    """Клавиатура в пределах лимитов VK: та же, если всё в порядке."""
    if not keyboard:
        return keyboard
    as_text = isinstance(keyboard, str)
    try:
        data = json.loads(keyboard) if as_text else dict(keyboard)
    except (TypeError, ValueError):
        return keyboard
    rows = data.get("buttons")
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        return keyboard
    fixed, problems = _fix_rows(rows, bool(data.get("inline")))
    if not problems:
        return keyboard
    labels = " | ".join(" / ".join(_label(b) for b in row) for row in rows if row)
    logger.error("Клавиатура не по лимитам VK ({}), исправлена при отправке: {}", "; ".join(problems), labels)
    data["buttons"] = fixed
    return json.dumps(data, ensure_ascii=False) if as_text else data
