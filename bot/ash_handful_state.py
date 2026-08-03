"""Патч 25, п.4: peer_id, у которых сейчас доступна несобранная горстка
пепла — одноразовая контекстная кнопка на карте. Сгорает, если игрок нажал
«Исследовать», не подобрав её (см. bot/handlers/world.py::explore)."""

_pending: set[int] = set()


def mark(peer_id: int) -> None:
    _pending.add(peer_id)


def is_pending(peer_id: int) -> bool:
    return peer_id in _pending


def clear(peer_id: int) -> bool:
    """True — была ожидающая находка (реально сгорела/собрана)."""
    if peer_id in _pending:
        _pending.discard(peer_id)
        return True
    return False
