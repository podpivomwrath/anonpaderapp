"""Формат % в бою (п.11): округление, клампы 0/100, health-bar."""

from game.combat import display


def test_pvp_whole_percent() -> None:
    assert display.hp_percent(500, 1000, display.MODE_PVP) == "50%"
    assert display.hp_percent(544, 1000, display.MODE_PVP) == "54%"


def test_raid_one_decimal() -> None:
    assert display.hp_percent(544, 1000, display.MODE_PVE_RAID) == "54.4%"


def test_never_zero_if_alive() -> None:
    assert display.hp_percent(1, 1000, display.MODE_PVP) == "1%"
    assert display.hp_percent(1, 10000, display.MODE_PVE_RAID) == "0.1%"


def test_never_hundred_if_wounded() -> None:
    assert display.hp_percent(999, 1000, display.MODE_PVP) == "99%"
    assert display.hp_percent(9999, 10000, display.MODE_PVE_RAID) == "99.9%"


def test_exact_bounds() -> None:
    assert display.hp_percent(1000, 1000) == "100%"
    assert display.hp_percent(0, 1000) == "0%"
    assert display.hp_percent(-5, 1000) == "0%"


def test_health_bar() -> None:
    bar = display.health_bar(500, 1000)
    assert "50%" in bar
    assert display.BAR_FILLED * 5 in bar
    # раненый не показывает полный бар, живой — пустой
    assert display.health_bar(999, 1000).startswith(display.BAR_FILLED * 9 + display.BAR_EMPTY)
    assert display.health_bar(1, 1000).startswith(display.BAR_FILLED)


def test_action_line_format() -> None:
    line = display.action_line("Ты", "наносишь удар", "Волк", 680, 540, 1000)
    assert line == "Ты наносишь удар → Волк: (-140 HP · 68% → 54%)"


def test_hp_delta_line_format() -> None:
    assert display.hp_delta_line(820, 680, 1000) == "(-140 HP · 82% → 68%)"
    assert display.hp_delta_line(610, 1000, 1000) == "(+390 HP · 61% → 100%)"


def test_xp_delta_line_format() -> None:
    assert display.xp_delta_line(45) == "(+45 опыта)"


def test_xp_penalty_line_format() -> None:
    assert display.xp_penalty_line(124, 0.2) == "(-124 опыта · 20%)"


def test_gold_delta_line_format() -> None:
    assert display.gold_delta_line(560, 3240) == "(+560 золота · всего 3240)"
    assert display.gold_delta_line(-20000, 27410) == "(-20000 золота · всего 27410)"


def test_max_hp_delta_line_format() -> None:
    assert display.max_hp_delta_line(520, 542) == "(Макс. здоровье: 520 → 542)"
