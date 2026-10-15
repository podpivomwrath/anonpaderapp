"""Очередь сообщений одного игрока (bot/peer_lock.py, 2026-10-15)."""

import asyncio

from bot import peer_lock


def _event(peer: int) -> dict:
    return {"type": "message_new", "object": {"message": {"peer_id": peer, "text": "x"}}}


class _View:
    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.active: dict[int, int] = {}
        self.max_active: dict[int, int] = {}
        self.order: list[tuple[int, str]] = []

    async def handle_event(self, event, ctx_api, state_dispenser):
        peer = event["object"]["message"]["peer_id"]
        self.active[peer] = self.active.get(peer, 0) + 1
        self.max_active[peer] = max(self.max_active.get(peer, 0), self.active[peer])
        self.order.append((peer, "start"))
        await asyncio.sleep(self.delay)
        self.order.append((peer, "end"))
        self.active[peer] -= 1


class _Api:
    def __init__(self):
        self.sent: list[dict] = []

        class _Messages:
            async def send(inner, **kwargs):
                self.sent.append(kwargs)

        self.messages = _Messages()


def test_same_peer_is_serialized_other_peers_parallel():
    peer_lock._locks.clear()
    view = _View()
    peer_lock.install(view)
    api = _Api()

    async def run():
        await asyncio.gather(
            view.handle_event(_event(1), api, None),
            view.handle_event(_event(1), api, None),
            view.handle_event(_event(2), api, None),
        )

    asyncio.run(run())
    # одно и то же нажатие дважды - строго по очереди
    assert view.max_active[1] == 1
    assert view.order.count((1, "start")) == 2
    # другой игрок не ждал первого
    first_end_1 = view.order.index((1, "end"))
    assert view.order.index((2, "start")) < first_end_1


def test_long_busy_peer_gets_wait_reply(monkeypatch):
    peer_lock._locks.clear()
    monkeypatch.setattr(peer_lock, "WAIT_SECONDS", 0.05)
    view = _View(delay=0.3)
    peer_lock.install(view)
    api = _Api()

    async def run():
        await asyncio.gather(
            view.handle_event(_event(5), api, None),
            view.handle_event(_event(5), api, None),
        )

    asyncio.run(run())
    assert view.order.count((5, "start")) == 1
    assert api.sent and api.sent[0]["message"] == peer_lock.BUSY_TEXT


def test_non_message_events_pass_through():
    peer_lock._locks.clear()
    view = _View(delay=0)
    peer_lock.install(view)
    asyncio.run(view.handle_event({"type": "message_new", "object": {"message": {"peer_id": 9}}}, _Api(), None))
    assert peer_lock._peer_of({"type": "group_join", "object": {}}) is None
