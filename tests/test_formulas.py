"""Формулы v2 (п.2 дизайна) — точные значения."""

import pytest

from game.combat import formulas


@pytest.mark.parametrize(
    "level,tier",
    [(1, "grey"), (15, "grey"), (16, "white"), (30, "white"), (31, "green"),
     (45, "green"), (46, "blue"), (60, "blue"), (61, "epic"), (80, "epic"),
     (81, "legendary"), (100, "legendary")],
)
def test_tier_for_level(level: int, tier: str) -> None:
    assert formulas.tier_for_level(level) == tier


def test_hp() -> None:
    # 60 + 22*1 + 8*15 + 30*1.0 = 232
    assert formulas.hp(1, 15, 1.0) == 232
    # 60 + 22*100 + 8*90 + 30*2.5 = 3055
    assert formulas.hp(100, 90, 2.5) == 3055


def test_damage() -> None:
    # weapon_base(1.0)=10; 10 + 2*15 = 40
    assert formulas.damage(1.0, 15, formulas.k_dmg_for("str")) == 40
    # разбойник: 10*2.5 + 1.5*100 = 175
    assert formulas.damage(2.5, 100, formulas.k_dmg_for("agi")) == 175


def test_caps() -> None:
    assert formulas.crit_chance(100) == pytest.approx(0.3)
    assert formulas.crit_chance(500) == 0.60          # потолок
    assert formulas.mitigation(100) == pytest.approx(0.2)
    assert formulas.mitigation(400) == 0.50           # потолок
    assert formulas.control_resist(50) == pytest.approx(0.5)
    assert formulas.control_resist(200) == 0.75       # потолок
    assert formulas.support_power(300) == pytest.approx(1.5)  # без потолка


def test_respawn_time() -> None:
    assert formulas.respawn_time_minutes(1) == pytest.approx(1.0)
    assert formulas.respawn_time_minutes(100) == pytest.approx(30.0)
    # линейность: середина диапазона
    mid = formulas.respawn_time_minutes(50)
    assert 15.0 < mid < 16.0
