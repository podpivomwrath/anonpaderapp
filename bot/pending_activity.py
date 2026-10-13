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


# --- Открытое событие исследования (2026-10-12) ---------------------------
# Сцена события («Раненый путник», «Снова пусто»...) ждёт нажатия, пока
# игрок не ответит - хоть через час. Жила она только в памяти, и после
# деплоя кнопка молча переставала работать (игрок Ruskiq: событие в 05:20,
# два нажатия в 06:07 - тишина). Здесь - какая сцена открыта и под каким
# токеном; токен совпал - сцена восстанавливается и нажатие срабатывает.
# Ключ не pending:*: восстановление занятий (pending()) его не трогает.
SCENE_TTL_SECONDS = 24 * 3600


def _scene_key(peer_id: int) -> str:
    return f"scene:{peer_id}"


async def remember_scene(peer_id: int, event_id: str, scene_id: str, token: int, mult: float = 1.0) -> None:
    if _redis is None:
        return
    await _redis.set(_scene_key(peer_id), f"{token}|{event_id}|{scene_id}|{mult}", ex=SCENE_TTL_SECONDS)


async def recall_scene(peer_id: int) -> tuple[int, str, str, float] | None:
    """(токен, событие, сцена, множитель награды) открытого события или None.
    Записи прежнего формата - без множителя (1.0)."""
    if _redis is None:
        return None
    raw = await _redis.get(_scene_key(peer_id))
    if raw is None:
        return None
    raw = raw.decode() if isinstance(raw, bytes) else raw
    parts = raw.split("|")
    mult = float(parts[3]) if len(parts) > 3 else 1.0
    return int(parts[0]), parts[1], parts[2], mult


async def forget_scene(peer_id: int) -> None:
    if _redis is None:
        return
    await _redis.delete(_scene_key(peer_id))


# События исследования с выбором (осколок, шкатулка, алтарь, путник...):
# какое событие ждёт ответа и, у «Рыбака у воды», по какой цене. Раньше жили
# только в памяти: рестарт - и кнопки выбора молча не работали (2026-10-13,
# игрок 74337389: событие в 06:49:43, рестарт в 06:49:55).
EVENT_TTL_SECONDS = 3600


def _event_key(peer_id: int) -> str:
    return f"evt:{peer_id}"


async def remember_event(peer_id: int, event_id: str, fish_multiplier: float | None) -> None:
    if _redis is None:
        return
    mult = "" if fish_multiplier is None else f"{fish_multiplier:.6f}"
    await _redis.set(_event_key(peer_id), f"{event_id}|{mult}", ex=EVENT_TTL_SECONDS)


async def recall_event(peer_id: int) -> tuple[str, float | None] | None:
    if _redis is None:
        return None
    # Забрать и удалить разом: два быстрых нажатия после рестарта не должны
    # оба получить событие (иначе награда дважды). Дальше оно живёт в памяти.
    raw = await _redis.getdel(_event_key(peer_id))
    if raw is None:
        return None
    raw = raw.decode() if isinstance(raw, bytes) else raw
    event_id, mult = raw.split("|", 1)
    return event_id, (float(mult) if mult else None)


async def forget_event(peer_id: int) -> None:
    if _redis is None:
        return
    await _redis.delete(_event_key(peer_id))


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
