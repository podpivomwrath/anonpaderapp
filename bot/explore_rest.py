"""Кто сейчас исследует клетку или отдыхает (2026-10-21: вынесено из
bot/handlers/world.py).

Отметка живёт в памяти процесса, а копия - в Redis (bot/pending_activity.py),
чтобы занятие пережило деплой. Раньше каждое место в world.py снимало
отметку и запись вручную, и забытая пара воскрешала отдых после следующего
деплоя. Теперь начать и снять занятие можно только здесь, обе половины
меняются вместе.
"""

from contextlib import contextmanager

from bot import pending_activity

EXPLORE, REST = "explore", "rest"

_peers: dict[str, set[int]] = {EXPLORE: set(), REST: set()}


def exploring(peer_id: int) -> bool:
    return peer_id in _peers[EXPLORE]


def resting(peer_id: int) -> bool:
    return peer_id in _peers[REST]


def busy(peer_id: int) -> bool:
    return exploring(peer_id) or resting(peer_id)


async def start(kind: str, peer_id: int, delay_seconds: float) -> None:
    """Отметка ставится до первого await - двойное нажатие уже видит занятость."""
    _peers[kind].add(peer_id)
    await pending_activity.remember(kind, peer_id, delay_seconds)
    if kind == "explore":
        await pending_activity.drop_vein(peer_id)


def restore(kind: str, peer_id: int) -> None:
    """После перезапуска: запись в Redis уже есть, вернуть только отметку."""
    _peers[kind].add(peer_id)


async def stop(kind: str, peer_id: int) -> bool:
    """Снять занятие. True - оно было."""
    was = peer_id in _peers[kind]
    _peers[kind].discard(peer_id)
    await pending_activity.forget(kind, peer_id)
    return was


async def drop(peer_id: int) -> None:
    """Снять всё (/застрял, смена фракции, покупка в магазине)."""
    await stop(EXPLORE, peer_id)
    await stop(REST, peer_id)


@contextmanager
def group_search(peer_ids: list[int]):
    """Группа ищет противника: все «исследуют», пока идёт поиск. Это ожидание
    внутри одного вызова, после рестарта его не возобновить - в Redis не пишем."""
    _peers[EXPLORE].update(peer_ids)
    try:
        yield
    finally:
        _peers[EXPLORE].difference_update(peer_ids)


def clear() -> None:
    """Для тестов."""
    for peers in _peers.values():
        peers.clear()
