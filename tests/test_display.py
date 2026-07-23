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
    assert line == "Ты наносишь удар → Волк: -14% (68% → 54%)"
