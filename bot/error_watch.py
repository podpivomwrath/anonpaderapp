"""Сводка ошибок бота (2026-10-21): сколько за час и сутки и какие чаще всего -
в обзоре админки, а при всплеске - весть администратору в чат.

Считается в памяти процесса (sink loguru уровня ERROR): после рестарта
счёт начинается заново. Полные тексты - в /app/logs/errors.log.
"""

import time
from collections import Counter, deque

from loguru import logger

#: Столько ошибок за час - уже всплеск, а не фон.
ALERT_PER_HOUR = 15
#: Повторная весть о всплеске - не чаще.
ALERT_COOLDOWN_SECONDS = 3 * 3600
DAY = 24 * 3600

_events: deque[tuple[float, str]] = deque(maxlen=5000)
_last_alert = 0.0
_installed = False


def _sink(message) -> None:
    record = message.record
    first = str(record["message"]).splitlines()[0][:120] if record["message"] else ""
    _events.append((time.time(), f"{record['name']}: {first}"))


def install() -> None:
    global _installed
    if not _installed:
        logger.add(_sink, level="ERROR", enqueue=False)
        _installed = True


def stats(now: float | None = None) -> dict:
    now = now or time.time()
    day = [(t, text) for t, text in _events if now - t <= DAY]
    hour = sum(1 for t, _ in day if now - t <= 3600)
    top = Counter(text for _, text in day).most_common(5)
    return {"hour": hour, "day": len(day), "top": [{"text": text, "count": n} for text, n in top]}


async def alert_job() -> None:
    """Раз в 10 минут: всплеск ошибок - весть администратору."""
    global _last_alert
    from config import get_settings

    from bot.handlers import world as world_handlers

    s = stats()
    admin = get_settings().admin_vk_id
    if not admin or s["hour"] < ALERT_PER_HOUR or time.time() - _last_alert < ALERT_COOLDOWN_SECONDS:
        return
    _last_alert = time.time()
    lines = [f"⚠️ Бот: {s['hour']} ошибок за последний час."]
    lines += [f"· {row['count']}× {row['text']}" for row in s["top"][:3]]
    try:
        await world_handlers.send_plain_notice(admin, "\n".join(lines))
    except Exception:  # noqa: BLE001
        logger.warning("Сводка ошибок: весть администратору не ушла")
