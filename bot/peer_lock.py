"""Сообщения одного игрока - строго по очереди (2026-10-15).

Callback API отдаёт каждое событие VK отдельной задачей, и два быстрых
нажатия одного игрока шли ПАРАЛЛЕЛЬНО: оба проходили проверки состояния
(«уже исследуешь?», «в бою?», «отдыхаешь?») до того, как первое успевало
его поменять. Отсюда двойные исследования, бои поверх боёв и прочие
«забагался». Чинить каждую кнопку по отдельности бесконечно, поэтому здесь
общий замок: следующее сообщение игрока обрабатывается только после того,
как закончено предыдущее, и видит уже новое состояние - а значит получает
честный ответ вида «ты уже осматриваешься».

Разные игроки по-прежнему обрабатываются параллельно.

Если предыдущее действие держит очередь дольше WAIT_SECONDS (пауза между
этапами рейда и т.п.), лишнее нажатие не копится, а получает «подожди».
"""

import asyncio

from loguru import logger

WAIT_SECONDS = 10.0
BUSY_TEXT = "⏳ Предыдущее действие ещё выполняется - подожди немного."

_locks: dict[int, asyncio.Lock] = {}


def _peer_of(event) -> int | None:
    if not isinstance(event, dict) or event.get("type") != "message_new":
        return None
    obj = event.get("object") or {}
    message = obj.get("message") if isinstance(obj, dict) else None
    peer = (message or obj).get("peer_id") if isinstance(message or obj, dict) else None
    try:
        return int(peer) if peer is not None else None
    except (TypeError, ValueError):
        return None


def install(view) -> None:
    """Обернуть handle_event вида сообщений (main.create_bot)."""
    original = view.handle_event

    async def handle_event(event, ctx_api, state_dispenser):
        peer = _peer_of(event)
        if peer is None:
            return await original(event, ctx_api, state_dispenser)
        lock = _locks.setdefault(peer, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), WAIT_SECONDS)
        except (asyncio.TimeoutError, TimeoutError):
            logger.info("Очередь игрока {} занята дольше {} сек - нажатие отклонено", peer, WAIT_SECONDS)
            try:
                await ctx_api.messages.send(peer_id=peer, message=BUSY_TEXT, random_id=0)
            except Exception:  # noqa: BLE001 - ответ «подожди» не должен ронять ничего
                logger.exception("Не удалось ответить «подожди» {}", peer)
            return None
        try:
            return await original(event, ctx_api, state_dispenser)
        finally:
            lock.release()

    view.handle_event = handle_event
