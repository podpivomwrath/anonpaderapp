"""Сверки связок, которые раньше расходились молча (2026-10-21).

Каждый тест ловит класс багов, который у нас уже случался: товар в каталоге
без покупки (Дом - bad_request), экран без восстановления клавиатуры,
кнопка без обработчика. Связки ищутся по исходникам: так проверка сама
видит новые экраны и кнопки, без ручного списка.
"""

import re
from pathlib import Path

from services import screen_service

ROOT = Path(__file__).resolve().parent.parent
BOT = {p: p.read_text(encoding="utf-8") for p in (ROOT / "bot").rglob("*.py")}

#: Экраны со своим «Назад» вне таблицы PARENT: озеро и рудник возвращают на
#: клетку, список рейдов - на площадь (их обработчики делают это сами).
OWN_BACK = {"lake", "mine", "raid_list"}


def _screens() -> set[str]:
    found = set()
    for src in BOT.values():
        found |= set(re.findall(r'set_screen\([^,()]+,\s*[^,()]+,\s*"([a-z_]+)"', src))
    return found


def _func_source(path: str, name: str) -> str:
    src = BOT[ROOT / path]
    start = src.index(f"def {name}(")
    end = src.find("\n\n\n", start)
    return src[start:end]


def test_every_screen_has_a_way_back() -> None:
    screens = _screens()
    assert len(screens) > 10  # поиск по исходникам не сломался
    missing = screens - set(screen_service.PARENT) - OWN_BACK
    assert not missing, f"экраны без «Назад» в screen_service.PARENT: {sorted(missing)}"
    # И родитель - тоже экран (или корень None).
    for child, parent in screen_service.PARENT.items():
        assert parent is None or parent in screen_service.PARENT or parent in OWN_BACK, (child, parent)


def test_every_screen_restores_its_keyboard() -> None:
    """/клавиатура и рестарт бота: экран, которого не знает _screen_keyboard
    (и ни один rebuild), получает клавиатуру карты поверх себя - тупик."""
    known = _func_source("bot/handlers/world.py", "_screen_keyboard")
    for path in ("bot/handlers/appraiser.py", "bot/handlers/elixir_shop.py", "bot/handlers/inventory.py",
                 "bot/handlers/house.py"):
        known += _func_source(path, "rebuild")
    missing = sorted(s for s in _screens() if f'"{s}"' not in known)
    assert not missing, f"экраны без восстановления клавиатуры: {missing}"


def test_every_payload_button_has_a_handler() -> None:
    sent: dict[str, str] = {}
    handled: set[str] = set()
    consts: dict[str, str] = {}
    for src in BOT.values():  # сначала все константы: объявлены и в чужих файлах
        consts.update(re.findall(r'^([A-Z_]+)\s*=\s*\{"type":\s*"([a-z_0-9]+)"', src, re.M))
    for path, src in BOT.items():
        handled |= set(re.findall(r'payload_contains=\{"type":\s*"([a-z_0-9]+)"', src))
        for name in re.findall(r"payload(?:_contains)?=(?:\w+\.)?([A-Z_]+)\)", src):
            if name in consts:
                handled.add(consts[name])
        if "Keyboard(" in src:
            for t in re.findall(r'\{"type":\s*"([a-z_0-9]+)"', src):
                sent.setdefault(t, path.name)
    # Обрабатывается по тексту кнопки (BTN_ASH_HANDFUL), payload - для отчётов.
    by_text = {"ash_handful"}
    missing = sorted(f"{t} ({f})" for t, f in sent.items() if t not in handled | by_text)
    assert len(sent) > 50
    assert not missing, f"кнопки без обработчика: {missing}"
