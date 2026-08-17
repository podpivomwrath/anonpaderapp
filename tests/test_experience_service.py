"""Опыт и уровни (progression-patch-4): формулы, левелап-цикл, штраф смерти."""

from dataclasses import dataclass

import pytest

from game.combat import balance_config as bc
from services import experience_service as svc


@dataclass
class FakeCharacter:
    level: int = 1
    experience: int = 0
    premium_until: object = None


@dataclass
class FakeStats:
    unspent_points: int = 0


# --- Формулы ---


def test_xp_curve_is_increasing_before_plateau() -> None:
    vals = [svc.xp_to_next(l) for l in range(1, 50)]
    assert all(b > a for a, b in zip(vals, vals[1:]))  # строго нарастает


def test_plateau_kink_at_50() -> None:
    # На 50 явный излом: требования скачком вырастают и дальше растут ЛИНЕЙНО
    # (замедляется скорость набора уровней — на прокачку уходит кратно больше).
    jump_at_50 = svc.xp_to_next(50) - svc.xp_to_next(49)
    pre_increment = svc.xp_to_next(49) - svc.xp_to_next(48)
    assert jump_at_50 > pre_increment * 5  # скачок кратно больше обычного шага

    # после 50 — линейная полка: приросты требований одинаковы (±1 от int())
    inc_51 = svc.xp_to_next(51) - svc.xp_to_next(50)
    inc_52 = svc.xp_to_next(52) - svc.xp_to_next(51)
    assert abs(inc_51 - inc_52) <= 1


def test_xp_per_mob_formula() -> None:
    assert svc.xp_per_mob(1) == bc.XP_MOB_FLAT + bc.XP_MOB_PER_LEVEL
    assert svc.xp_per_mob(10) == bc.XP_MOB_FLAT + bc.XP_MOB_PER_LEVEL * 10


# --- Патч 26: опыт за разницу уровней ---


def test_mob_xp_level_diff_multiplier_no_bonus_at_or_below_player_level() -> None:
    assert svc.mob_xp_level_diff_multiplier(7, 7) == 1.0
    assert svc.mob_xp_level_diff_multiplier(3, 7) == 1.0


def test_mob_xp_level_diff_multiplier_scales_and_caps() -> None:
    assert svc.mob_xp_level_diff_multiplier(16, 7) == pytest.approx(1 + 0.08 * 9)
    assert svc.mob_xp_level_diff_multiplier(100, 1) == bc.XP_LEVEL_DIFF_CAP


def test_xp_for_kill_applies_multiplier() -> None:
    xp, mult = svc.xp_for_kill(16, 7)
    assert mult == pytest.approx(1 + 0.08 * 9)
    assert xp == int(svc.xp_per_mob(16) * mult)


def test_xp_for_kill_no_bonus_own_level() -> None:
    xp, mult = svc.xp_for_kill(7, 7)
    assert mult == 1.0
    assert xp == svc.xp_per_mob(7)


def test_event_xp_is_share_of_xp_for_kill() -> None:
    """Патч 36: опыт события — доля от xp_for_kill(zone_level, player_level),
    включая множитель за разницу уровней (не от xp_per_mob(player_level))."""
    base, _ = svc.xp_for_kill(16, 7)
    assert svc.event_xp(16, 7, 0.5) == round(base * 0.5)


def test_event_xp_zero_share_is_zero() -> None:
    assert svc.event_xp(10, 10, 0.0) == 0


# --- Левелап ---


def test_single_level_up() -> None:
    char, stats = FakeCharacter(level=1), FakeStats()
    need = svc.xp_to_next(1)
    result = svc.add_experience(char, stats, need)
    assert result.levels_gained == 1
    assert char.level == 2
    assert char.experience == 0  # опыт перенесён без остатка
    assert stats.unspent_points == bc.STAT_POINTS_PER_LEVEL


def test_experience_carries_remainder() -> None:
    char, stats = FakeCharacter(level=1), FakeStats()
    need = svc.xp_to_next(1)
    svc.add_experience(char, stats, need + 10)
    assert char.level == 2
    assert char.experience == 10  # остаток в новом уровне


def test_multi_level_in_one_award() -> None:
    char, stats = FakeCharacter(level=1), FakeStats()
    big = svc.xp_to_next(1) + svc.xp_to_next(2) + svc.xp_to_next(3)
    result = svc.add_experience(char, stats, big)
    assert result.levels_gained == 3
    assert char.level == 4
    assert stats.unspent_points == bc.STAT_POINTS_PER_LEVEL * 3


def test_partial_xp_no_level() -> None:
    char, stats = FakeCharacter(level=1), FakeStats()
    result = svc.add_experience(char, stats, svc.xp_to_next(1) - 1)
    assert result.levels_gained == 0
    assert char.level == 1


def test_capped_at_max_level() -> None:
    char = FakeCharacter(level=bc.MAX_LEVEL, experience=0)
    stats = FakeStats()
    result = svc.add_experience(char, stats, 10_000_000)
    assert char.level == bc.MAX_LEVEL
    assert result.levels_gained == 0
    assert char.experience == 0  # на потолке не копится


# --- Штраф смерти ---


def test_death_penalty_20_percent_of_current_level() -> None:
    char = FakeCharacter(level=5, experience=1000)
    lost = svc.apply_death_penalty(char)
    assert lost == 200  # 20% от опыта ТЕКУЩЕГО уровня
    assert char.experience == 800
    assert char.level == 5  # уровень не падает


def test_death_penalty_never_below_zero() -> None:
    char = FakeCharacter(level=3, experience=0)
    lost = svc.apply_death_penalty(char)
    assert lost == 0
    assert char.experience == 0
