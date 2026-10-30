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
    # Движок дуэли: яд в начале хода, удар, три вида возврата (блок, «Кровь
    # за кровь», руна «Колючая броня») - каждое уже прошло через щиты и
    # потолок урона (shared_rules).
    "duel_engine.py": 5,
    # Пепельная лихорадка - самоурон эликсира, щиты его не держат по задумке.
    "resolver.py": 1,
    # Вспышка яда напоследок - после absorb_by_shields.
    "shared_rules.py": 1,
    # Разлом: взрыв осколка (после щитов) и раскол Двойника (HP босса делится).
    "rift.py": 2,
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
