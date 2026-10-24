"""Патч 25, п.4: peer_id, у которых сейчас доступна несобранная горстка
пепла — одноразовая контекстная кнопка на карте. Сгорает, если игрок нажал
«Исследовать», не подобрав её (см. bot/handlers/world.py::explore), или ушёл
с клетки (2026-10-24: кнопка жила в чате, и горстку подбирали где угодно).
"""

# peer_id -> клетка, где лежит горстка (None - клетка не записана)
_pending: dict[int, tuple[int, int] | None] = {}


def mark(peer_id: int, cell: tuple[int, int] | None = None) -> None:
    _pending[peer_id] = cell


def is_pending(peer_id: int) -> bool:
    return peer_id in _pending


def is_here(peer_id: int, cell: tuple[int, int]) -> bool:
    """Горстка есть и лежит на этой клетке."""
    if peer_id not in _pending:
        return False
    where = _pending[peer_id]
    return where is None or where == cell


def clear(peer_id: int) -> bool:
    """True — была ожидающая находка (реально сгорела/собрана)."""
    if peer_id in _pending:
        del _pending[peer_id]
        return True
    return False
