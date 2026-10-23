"""/помощь перечисляет все команды бота (2026-10-21)."""

import re
from pathlib import Path

from bot.handlers.basic import HELP_TEXT

ROOT = Path(__file__).resolve().parent.parent

#: Синонимы и служебные команды - в справке не нужны.
NOT_IN_HELP = {
    "/start", "/разлом", "/заказы", "/клавиатура", "/помощь", "/команды", "/баг",
}


def _commands_in_handlers() -> set[str]:
    found = set()
    for path in (ROOT / "bot" / "handlers").glob("*.py"):
        code = path.read_text(encoding="utf-8")
        for line in code.splitlines():
            if "@labeler.message(" not in line:
                continue
            found |= set(re.findall(r'"(/[а-яё]+)', line))
            found |= {f"/{w}" for w in re.findall(r"/\(\?:([а-яё]+)\|", line)}
    for name in ("fishing_texts", "mining_texts", "raid_texts"):
        found |= set(re.findall(r'_COMMAND = "(/[а-яё]+)"', (ROOT / "bot" / f"{name}.py").read_text(encoding="utf-8")))
    return found


def test_every_russian_command_is_in_help() -> None:
    commands = _commands_in_handlers()
    assert "/застрял" in commands and "/рыба" in commands  # разбор не сломался
    missing = sorted(c for c in commands - NOT_IN_HELP if c not in HELP_TEXT)
    assert not missing, f"нет в /помощь: {missing}"


def test_relics_command_lists_grades_and_total() -> None:
    """/реликвии (2026-10-23): реликвии по ступеням и цена у скупщика."""
    from bot.handlers.appraiser import RELICS_EMPTY_TEXT, relics_text
    from services import trophy_service

    defs = trophy_service.trophy_defs_ordered()[:2]
    text = relics_text([(defs[0], 3), (defs[1], 1)], 1.0, foreign=False)
    total = defs[0].sell_price * 3 + defs[1].sell_price
    assert defs[0].name in text and f"Всё вместе: {total} зол." in text
    assert relics_text([], 1.0, foreign=False) == RELICS_EMPTY_TEXT
    assert "родном городе" in relics_text([(defs[0], 1)], 0.8, foreign=True)
