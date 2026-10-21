"""Reservations for activity transitions in the single bot process.

Reserve synchronously before the first await; other actions cannot pass their
checks while a battle/trip is still being constructed. Nested starts share the
reservation owner, including group and raid participants.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_owners: dict[int, object] = {}
_owner: ContextVar[object | None] = ContextVar("activity_owner", default=None)


class ActivityBusy(ValueError):
    pass


@contextmanager
def transition(peer_ids):
    owner = _owner.get() or object()
    peers = set(peer_ids)
    if any(p in _owners and _owners[p] is not owner for p in peers):
        raise ActivityBusy("Действие ещё выполняется. Подожди немного.")
    added = peers - _owners.keys()
    for peer in added:
        _owners[peer] = owner
    token = _owner.set(owner)
    try:
        yield
    finally:
        for peer in added:
            _owners.pop(peer, None)
        _owner.reset(token)


def activity_action(handler):
    @wraps(handler)
    async def wrapped(message, *args, **kwargs):
        from bot.battle_keyboard import active_battle_keyboard
        try:
            with transition([message.peer_id]):
                return await handler(message, *args, **kwargs)
        except ActivityBusy as exc:
            await message.answer(str(exc), keyboard=active_battle_keyboard(message.peer_id))
    return wrapped


async def blocked_reason(db, character, peer_id: int) -> str | None:
    """Текст отказа, если игрок чем-то занят. Само состояние - bot/busy.py,
    одна проверка на весь бот (2026-10-21)."""
    from bot.busy import busy

    found = await busy(db, character, peer_id)
    return found.text if found is not None else None
