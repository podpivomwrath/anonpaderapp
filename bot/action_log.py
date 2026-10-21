"""Последние действия игрока в чате (2026-10-21): что прислал и прочитал ли
бот. Для разбора жалоб «бот не отвечает»: дошло ли нажатие до бота вообще
или отсеялось фильтром кнопок (bot/button_gate.py).

В Redis, по 20 записей на игрока, живут двое суток. Без Redis (тесты,
локальный запуск) молча выключено.
"""

import json
import time

from loguru import logger

KEEP = 20
TTL_SECONDS = 2 * 24 * 3600

_redis = None


def setup(redis) -> None:
    global _redis
    _redis = redis


def _key(peer_id: int) -> str:
    return f"actions:{peer_id}"


def entry(message, accepted: bool) -> dict:
    payload = message.payload
    kind = "кнопка" if payload else ("команда" if (message.text or "").lstrip().startswith("/") else "текст")
    return {"at": int(time.time()), "kind": kind, "text": (message.text or "")[:60], "accepted": accepted}


async def record(message, accepted: bool) -> None:
    if _redis is None or message.peer_id != message.from_id:
        return
    try:
        key = _key(message.peer_id)
        await _redis.lpush(key, json.dumps(entry(message, accepted), ensure_ascii=False))
        await _redis.ltrim(key, 0, KEEP - 1)
        await _redis.expire(key, TTL_SECONDS)
    except Exception:  # noqa: BLE001 - журнал не должен ронять обработку сообщения
        logger.exception("Журнал действий: не записалось {}", message.peer_id)


async def recent(peer_id: int) -> list[dict]:
    if _redis is None or peer_id is None:
        return []
    try:
        rows = await _redis.lrange(_key(peer_id), 0, KEEP - 1)
    except Exception:  # noqa: BLE001
        return []
    return [json.loads(r) for r in rows]
