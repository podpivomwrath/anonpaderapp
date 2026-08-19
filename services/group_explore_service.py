"""Групповое исследование (патч 51, ч.3): очередь готовности на общей
клетке. Состояние — в памяти процесса (как bot/ash_handful_state.py и
_pending_events в bot/handlers/world.py), не в БД: эфемерная координация одной
попытки исследования, переживать рестарт бота не обязана.

Участвуют ТОЛЬКО участники группы, находящиеся на ОДНОЙ клетке с нажавшим
[🔍 Исследовать] (кохорт фиксируется в момент старта очереди — присоединившиеся
позже физически на клетке считаются "опоздавшими", см. cancel/start_or_join)."""

from dataclasses import dataclass, field


@dataclass
class ReadyQueue:
    group_id: int
    cell: tuple[int, int]
    cohort: set[int]  # character_id — кто был на клетке при старте очереди
    ready: set[int] = field(default_factory=set)


_queues: dict[int, ReadyQueue] = {}


def is_queued(group_id: int) -> bool:
    return group_id in _queues


def get_queue(group_id: int) -> ReadyQueue | None:
    return _queues.get(group_id)


def start_or_join(
    group_id: int, cell: tuple[int, int], cohort_ids: set[int], character_id: int,
) -> ReadyQueue | None:
    """Первый нажавший [🔍 Исследовать] создаёт очередь на весь кохорт (все
    участники группы на этой клетке в этот момент); последующие нажатия из
    ТОГО ЖЕ кохорта присоединяются. None — character_id не входит в уже
    существующий кохорт (опоздавший или уже отменивший участие) — вызывающий
    код должен ответить блокирующим сообщением, не трогая очередь."""
    existing = _queues.get(group_id)
    if existing is not None:
        if character_id not in existing.cohort:
            return None
        existing.ready.add(character_id)
        return existing
    queue = ReadyQueue(group_id=group_id, cell=cell, cohort=set(cohort_ids), ready={character_id})
    _queues[group_id] = queue
    return queue


def cancel(group_id: int, character_id: int) -> None:
    """Убирает character_id из очереди — И из кохорта (патч 51, ч.3: "то же
    для игрока, отменившего участие и решившего исследовать заново, пока
    группа занята" — повторное нажатие должно считаться опоздавшим, не
    молча пересоздавать участие). Очередь остальных не сбрасывается —
    счётчик просто уменьшается; если кохорт опустел целиком, очередь
    удаляется."""
    queue = _queues.get(group_id)
    if queue is None:
        return
    queue.ready.discard(character_id)
    queue.cohort.discard(character_id)
    if not queue.cohort:
        _queues.pop(group_id, None)


def is_ready_to_start(queue: ReadyQueue) -> bool:
    return bool(queue.cohort) and queue.ready >= queue.cohort


def clear(group_id: int) -> None:
    _queues.pop(group_id, None)


def co_located_members(members: list, pos_x: int, pos_y: int) -> list:
    """members — services/group_service.py::GroupSnapshot.members (Character
    ORM-объекты, себя включает). Возвращает тех, кто на клетке (pos_x, pos_y)."""
    return [m for m in members if m.pos_x == pos_x and m.pos_y == pos_y]
