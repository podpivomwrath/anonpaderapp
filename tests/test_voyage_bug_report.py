"""Баг-репорт проходит и в долгом пути (2026-10-16)."""

from types import SimpleNamespace

from bot.handlers import voyage


def test_away_block_lets_bug_reports_through():
    voyage._away.add(777)
    try:
        msg = lambda text: SimpleNamespace(peer_id=777, text=text)  # noqa: E731
        assert voyage._is_bug_report(msg("/баг всё сломалось"))
        assert voyage._is_bug_report(msg("/BUG"))
        assert not voyage._is_bug_report(msg("Осмотреться"))
    finally:
        voyage._away.discard(777)
