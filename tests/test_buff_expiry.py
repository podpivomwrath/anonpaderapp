"""Репорт 262 (2026-10-31): конец баффа со сроком - сообщением, один раз."""

from datetime import datetime, timedelta, timezone

from services import buffs_service

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


async def test_expired_reports_once_in_window(db_session, make_character) -> None:
    c = await make_character(level=10)
    c.bait_until = NOW - timedelta(seconds=30)
    c.ash_tincture_until = NOW + timedelta(minutes=5)
    await db_session.flush()
    found = await buffs_service.expired(db_session, NOW - timedelta(minutes=1), NOW)
    assert found == [(c.id, ["🪱 Прикормка кончилась."])]
    # Следующее окно - уже без неё.
    assert await buffs_service.expired(db_session, NOW, NOW + timedelta(minutes=1)) == []
