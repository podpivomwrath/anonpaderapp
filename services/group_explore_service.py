"""Групповое исследование (патч 51, ч.3): очередь готовности на общей
клетке. Состояние — в памяти процесса (как bot/ash_handful_state.py и
_pending_events в bot/handlers/world.py), не в БД: эфемерная координация одной
попытки исследования, переживать рестарт бота не обязана.

Участвуют ТОЛЬКО участники группы, находящиеся на ОДНОЙ клетке с нажавшим
[🔍 Исследовать]. Кохорт сверяется с группой при КАЖДОМ нажатии (2026-10-12):
раньше он фиксировался при старте очереди, и игрок, вышедший из группы, так
и оставался в нём - остальные ждали его вечно, а отменивший участие и
нажавший снова получал «группа уже в деле» (инцидент Кирамус/Ruskiq/
ТайноДернул: у одного упала сеть, он вышел, двое застряли)."""

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
) -> ReadyQueue:
    """Первый нажавший [🔍 Исследовать] создаёт очередь на весь кохорт (все
    участники группы на этой клетке в этот момент); следующие нажатия
    присоединяются. cohort_ids - кто СЕЙЧАС в группе и на клетке: ушедшие из
    группы или с клетки из очереди выпадают, а нажавший - всегда в ней, даже
    если раньше отменил участие или пришёл позже."""
    existing = _queues.get(group_id)
    # Очередь, где никто не готов, - старая: в ней остался урезанный состав
    # после отмен (отдых тоже отменяет). Её собираем заново на всех, кто
    # на клетке. Иначе нажавший первым после отдыха шёл один, а напарник
    # ждал его в новой очереди (репорт 2026-10-14).
    if existing is not None and existing.cell == cell and existing.ready:
        existing.cohort = (existing.cohort & set(cohort_ids)) | {character_id}
        existing.ready = (existing.ready & existing.cohort) | {character_id}
        return existing
    queue = ReadyQueue(group_id=group_id, cell=cell, cohort=set(cohort_ids), ready={character_id})
    _queues[group_id] = queue
    return queue


def cancel(group_id: int, character_id: int) -> set[int]:
    """Игрок отменил участие или ушёл из группы: убрать его из очереди и из
    кохорта, чтобы остальные не ждали. Нажмёт снова - вернётся (start_or_join).

    Возвращает готовых, если без него очередь собралась целиком: им надо
    сказать нажать ещё раз - сам по себе бой не начнётся. Иначе пусто."""
    queue = _queues.get(group_id)
    if queue is None:
        return set()
    queue.ready.discard(character_id)
    queue.cohort.discard(character_id)
    if not queue.cohort:
        _queues.pop(group_id, None)
        return set()
    return set(queue.ready) if is_ready_to_start(queue) else set()


def is_ready_to_start(queue: ReadyQueue) -> bool:
    return bool(queue.cohort) and queue.ready >= queue.cohort


def clear(group_id: int) -> None:
    _queues.pop(group_id, None)


def co_located_members(members: list, pos_x: int, pos_y: int) -> list:
    """members — services/group_service.py::GroupSnapshot.members (Character
    ORM-объекты, себя включает). Возвращает тех, кто на клетке (pos_x, pos_y)."""
    return [m for m in members if m.pos_x == pos_x and m.pos_y == pos_y]
