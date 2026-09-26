"""Незавершённые исследование и отдых, пережившие перезапуск бота (патч 98).

Оба занятия живут только в памяти процесса: множество занятых игроков и
отложенная задача планировщика. Деплой стирал и то и другое, а у игрока на
экране оставалась клавиатура ожидания без единой кнопки. Исследование не
заканчивалось никогда, отдых - тоже, и снаружи это было неотличимо от
мёртвого бота. При десятке деплоев в день - не теория.

Здесь хранится только одно: кто чем занят и когда оно должно закончиться.
В Redis, потому что он живёт в своём контейнере и деплой бота его не
трогает. Этого хватает, чтобы после перезапуска вернуть игрока в занятие и
дослать завершение ровно тогда, когда оно и должно было прийти.

Без Redis (тесты, локальный запуск) всё это молча выключено: занятия
работают как раньше, просто не переживают перезапуск.
"""

from datetime import datetime, timezone

KINDS = ("explore", "rest")
_PREFIX = "pending"

_redis = None


def setup(redis) -> None:
    global _redis
    _redis = redis


def _key(kind: str, peer_id: int) -> str:
    return f"{_PREFIX}:{kind}:{peer_id}"


async def remember(kind: str, peer_id: int, delay_seconds: float) -> None:
    if _redis is None:
        return
    due = datetime.now(timezone.utc).timestamp() + delay_seconds
    # Срок жизни с запасом: если завершение по какой-то причине так и не
    # случится, запись не должна висеть вечно и воскрешать занятие через
    # неделю.
    await _redis.set(_key(kind, peer_id), f"{due:.3f}", ex=int(delay_seconds) + 3600)


async def forget(kind: str, peer_id: int) -> None:
    if _redis is None:
        return
    await _redis.delete(_key(kind, peer_id))


async def pending() -> list[tuple[str, int, float]]:
    """(вид, peer_id, сколько секунд осталось; 0 - уже пора)."""
    if _redis is None:
        return []
    now = datetime.now(timezone.utc).timestamp()
    found: list[tuple[str, int, float]] = []
    async for key in _redis.scan_iter(match=f"{_PREFIX}:*"):
        key = key.decode() if isinstance(key, bytes) else key
        _, kind, peer = key.split(":", 2)
        if kind not in KINDS:
            continue
        raw = await _redis.get(key)
        if raw is None:
            continue
        raw = raw.decode() if isinstance(raw, bytes) else raw
        found.append((kind, int(peer), max(0.0, float(raw) - now)))
    return found
