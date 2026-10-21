"""Ночная проверка баланса: коридоры по ролям (2026-10-21)."""

from tools import balance_check as bcheck


def test_corridors_by_role() -> None:
    ok = {"blood_knight": {"duel": 0.6, "solo": 0.9}, "guardian": {"duel": 0.2, "solo": 0.5}}
    assert bcheck.verdict(ok) == []
    bad = {"blood_knight": {"duel": 0.84, "solo": 0.3}, "guardian": {"duel": 0.5, "solo": 0.5}}
    problems = bcheck.verdict(bad)
    assert len(problems) == 3 and "Кровавый рыцарь: дуэль 84%" in problems[0]
