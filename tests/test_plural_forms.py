"""Фильтр склеек «число + слово» и «название + ларец» (2026-10-23, владелец:
«поставь на будущее фильтр, чтобы такого не было»).

В игре висели «1 убийств», «2 самоцветов», «Свиток ларец», «в Шепчущие
Пущи». Тест ищет в коде бота и мини-аппа подстановку переменной прямо перед
словом в одной падежной форме. Число из данных игрока бывает любым, и форма
слова должна идти через game/plural.py (в мини-аппе - своя функция-склонялка
рядом). Константы конфига (ЗАГЛАВНЫЕ) пропускаем: их значение известно и
проверено. Ложное срабатывание - строка в ALLOWED с причиной.
"""

import re
from pathlib import Path

from services import lootbox_service

ROOT = Path(__file__).resolve().parent.parent

#: Слова, у которых после числа меняется форма (1 очко / 2 очка / 5 очков).
WORDS = (
    "очков|очка|самоцветов|самоцвета|убийств|убийства|побед|победы|поражений|игроков|игрока|"
    "участников|участника|зарядов|заряда|ящиков|ларцов|ларца|меток|метки|мобов|моба|клеток|клетки|"
    "ходов|хода|часов|часа|дней|дня|порций|порции|зелий|кусков|куска|реликвий|трофеев|трофея|"
    "предметов|предмета|вещей|боёв|раз|штук|монет|голосов|заказов"
)
PY = re.compile(r"\{([^{}]{1,60})\} (?:" + WORDS + r")\b")
JS = re.compile(r"\$\{([^{}]{1,60})\} (?:" + WORDS + r")\b")
#: Константа конфига или литерал - значение известно заранее.
CONST = re.compile(r"^[\w.]*[A-Z][A-Z0-9_]+$|^\d+$")

#: "файл:фрагмент" - разрешённые места, с причиной.
ALLOWED = {
    # «до 5 игроков» - максимум разлома всегда 5+ (rift_config), форма верна.
    "bot/rift_texts.py:{t.max_size} игроков",
    "services/rift_service.py:{t.max_size} игроков",
    # Админка: видит только владелец, «3 раз» его не смущает.
    "miniapp/src/components/AdminTab.jsx:",
    # Интервал «1-3 самоцветов» - строка, не число.
    "services/lootbox_service.py:{span} самоцветов",
    # Докстринг, не текст игрока.
    "game/world/group_events.py:{id: имя} участников",
}


def _allowed(rel: str, hit: str) -> bool:
    return any(rel.startswith(a.split(":", 1)[0]) and (not a.split(":", 1)[1] or a.split(":", 1)[1] in hit)
               for a in ALLOWED)


def _scan(paths, pattern) -> list[str]:
    bad = []
    for path in paths:
        rel = path.relative_to(ROOT).as_posix()
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(("#", "//", "*")):
                continue
            for m in pattern.finditer(line):
                expr = m.group(1).strip()
                if CONST.match(expr) or _allowed(rel, m.group(0)):
                    continue
                bad.append(f"{rel}:{no}: {m.group(0)}")
    return bad


def test_no_fixed_plural_after_variable_in_python() -> None:
    files = [p for d in ("bot", "services", "game") for p in (ROOT / d).rglob("*.py")]
    bad = _scan(files, PY)
    assert not bad, "число из данных перед словом в одной форме - через game/plural.py:\n" + "\n".join(bad)


def test_no_fixed_plural_after_variable_in_miniapp() -> None:
    files = [p for p in (ROOT / "miniapp" / "src").rglob("*") if p.suffix in (".js", ".jsx")]
    bad = _scan(files, JS)
    assert not bad, "число перед словом в одной форме - нужна склонялка:\n" + "\n".join(bad)


def test_chest_grade_titles() -> None:
    """Существительное не склеивается с «ларец»: «Свиток», а не «Свиток ларец»."""
    assert lootbox_service.grade_title("Пыльный") == "Пыльный ларец"
    assert lootbox_service.grade_title("Свиток") == "Свиток"
    for kind in lootbox_service.CHEST_KINDS:
        for grade in lootbox_service._load(kind):
            title = lootbox_service.grade_title(grade.name)
            words = title.split()
            assert not (len(words) > 1 and words[-1] == "ларец" and not words[-2].endswith(("ый", "ий", "ой"))), title
