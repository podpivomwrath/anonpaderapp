"""Места в топах вчера (2026-10-22): стрелки ▲3 / ▼1 у строк топа в мини-аппе.

Снимок мест каждой доски кладётся в Redis при первом запросе топа за день
(по Москве) и живёт трое суток. Изменение места - разница со вчерашним
снимком: «вчера» значит «на момент первого взгляда на топ вчера», точнее и
не нужно. Нет Redis или нет вчерашнего снимка - стрелок просто нет.
"""

from loguru import logger

from services.daily_service import today_msk

_redis = None
TTL_SECONDS = 3 * 24 * 3600


def setup(redis) -> None:
    global _redis
    _redis = redis


def _key(board_id: str, day) -> str:
    return f"top_places:{board_id}:{day.isoformat()}"


async def deltas(board_id: str, ranking: dict[int, int]) -> dict[int, int]:
    """{character_id: на сколько мест поднялся со вчера} (минус - опустился).
    Заодно снимает сегодняшний снимок, если его ещё нет."""
    if _redis is None or not ranking:
        return {}
    from datetime import timedelta

    today = today_msk()
    try:
        key = _key(board_id, today)
        if not await _redis.exists(key):
            await _redis.hset(key, mapping={str(cid): rank for cid, rank in ranking.items()})
            await _redis.expire(key, TTL_SECONDS)
        before = await _redis.hgetall(_key(board_id, today - timedelta(days=1)))
    except Exception as exc:  # стрелки - украшение, топ без них работает
        logger.warning("top_places: Redis недоступен: {}", exc)
        return {}
    out = {}
    for raw_id, raw_rank in before.items():
        cid = int(raw_id.decode() if isinstance(raw_id, bytes) else raw_id)
        if cid in ranking:
            out[cid] = int(raw_rank) - ranking[cid]
    return out
