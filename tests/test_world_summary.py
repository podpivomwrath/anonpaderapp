"""Сводка локации и шкала опыта (ux-patch-5)."""

import random
from dataclasses import dataclass

from bot import world_summary
from game.combat import balance_config as bc
from services import experience_service


@dataclass
class FakeChar:
    pos_x: int = 49
    pos_y: int = 49
    region: str = "ridge"
    level: int = 1
    experience: int = 0
    current_hp: int | None = None


@dataclass
class FakeStats:
    vitality: int = 15


def test_xp_bar_format() -> None:
    bar = world_summary.xp_bar(2, 100)
    assert bar.startswith("✨ Опыт:")
    assert "/" in bar and "%" in bar
    # процент — целое
    percent = bar.split("(")[1].rstrip("%)")
    assert percent.isdigit()


def test_xp_bar_fill_matches_ratio() -> None:
    need = experience_service.xp_to_next(1)
    half = world_summary.xp_bar(1, need // 2)
    assert world_summary.display.BAR_FILLED * 5 in half  # ~50% заполнения


def test_xp_bar_thousands_separator() -> None:
    bar = world_summary.xp_bar(50, 12_345)
    assert "12 345" in bar  # пробел как разделитель тысяч


def test_xp_bar_max_level() -> None:
    assert world_summary.xp_bar(bc.MAX_LEVEL, 0) == "✨ Опыт: МАКС"


def test_location_summary_structure() -> None:
    text = world_summary.location_summary(
        FakeChar(level=3, experience=100), FakeStats(), random.Random(1), farm_currency=340
    )
    assert "📍 (49; 49)" in text          # координаты
    assert " · зона 1-15 ур." in text     # тип локации + зона
    assert "❤️ Здоровье:" in text         # HP-бар (патч 10)
    assert "⚔️ Уровень: 3" in text        # уровень
    assert "✨ Опыт:" in text             # шкала опыта
    assert "💰 Золото: 340" in text       # баланс золота (патч 9)
    assert text.count("━━━━━━━━━━━━━━") == 2  # рамка вокруг блока стат
    # порядок блока статуса: Здоровье -> Уровень -> Опыт -> Золото
    hp_pos = text.index("❤️ Здоровье:")
    level_pos = text.index("⚔️ Уровень:")
    xp_pos = text.index("✨ Опыт:")
    gold_pos = text.index("💰 Золото:")
    assert hp_pos < level_pos < xp_pos < gold_pos


def test_location_summary_has_description() -> None:
    text = world_summary.location_summary(FakeChar(), FakeStats(), random.Random(1), farm_currency=0)
    lines = text.splitlines()
    # вторая строка — вариативное описание локации (непустое, не координаты)
    assert lines[1] and not lines[1].startswith("📍")


def test_location_summary_full_hp_shows_100_percent() -> None:
    text = world_summary.location_summary(
        FakeChar(current_hp=None), FakeStats(), random.Random(1), farm_currency=0
    )
    assert "100%" in text
