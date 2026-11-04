"""Сверка (2026-10-22): здоровье в бою меняется только в известных местах.

Механики рейдов раньше снимали HP напрямую и шли мимо щитов («Цитата»
Архивариуса, цепь и ответ генерала в Безмогильном поле, возврат урона).
Урон механики - через raid_field.stage_hurt (щиты, «Последний вздох», гибель);
новое прямое `current_hp -=` в game/combat - только с причиной в списке ниже.
"""

import re
from pathlib import Path

COMBAT = Path(__file__).resolve().parents[1] / "game" / "combat"

#: файл -> сколько прямых вычитаний там разрешено и почему.
ALLOWED = {
    # Пепельная лихорадка - самоурон эликсира, щиты его не держат по задумке.
    "resolver.py": 1,
    # Вспышка яда напоследок - после absorb_by_shields.
    "shared_rules.py": 1,
    # Разлом: раскол Двойника (HP босса делится).
    "rift.py": 1,  # взрыв осколка - через stage_hurt с 2026-11-05
    # Мельник: цепь забирает лечение прикованного, не урон (не ниже 1 HP).
    "raid_mill.py": 1,
}


def test_direct_hp_subtraction_only_in_known_places() -> None:
    found = {}
    for path in COMBAT.glob("*.py"):
        n = len(re.findall(r"current_hp\s*-=", path.read_text(encoding="utf-8")))
        if n:
            found[path.name] = n
    assert found == ALLOWED, (
        "прямое current_hp -= в бою: урон механики - через raid_field.stage_hurt, "
        f"иначе он идёт мимо щитов. Сейчас {found}"
    )
