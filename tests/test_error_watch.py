"""Сводка ошибок для админки и весть о всплеске (2026-10-21)."""

from loguru import logger

from bot import error_watch


async def test_counts_errors_and_alerts_once(monkeypatch) -> None:
    monkeypatch.setattr(error_watch, "_events", error_watch.deque(maxlen=100))
    monkeypatch.setattr(error_watch, "_last_alert", 0.0)
    error_watch.install()
    for _ in range(error_watch.ALERT_PER_HOUR):
        logger.error("Разломы: тик не прошёл")
    logger.warning("это не ошибка")
    s = error_watch.stats()
    assert s["hour"] == error_watch.ALERT_PER_HOUR and s["top"][0]["count"] == error_watch.ALERT_PER_HOUR

    sent = []

    async def notice(peer, text):
        sent.append((peer, text))

    from bot.handlers import world as world_handlers
    from config import get_settings

    monkeypatch.setattr(world_handlers, "send_plain_notice", notice)
    monkeypatch.setattr(get_settings(), "admin_vk_id", 42)
    await error_watch.alert_job()
    await error_watch.alert_job()  # повтор - не раньше, чем через 3 часа
    assert len(sent) == 1 and sent[0][0] == 42 and "ошибок за последний час" in sent[0][1]
