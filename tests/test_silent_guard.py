"""Страховка от «немых» кнопок (2026-10-13): если бот ничего не ответил на
сообщение в личке, игрок получает свежую клавиатуру; ответил - молчим."""

import time

from bot import silent_guard


class FakeApi:
    def __init__(self):
        self.calls = []

    async def request(self, method, data, version=None):
        self.calls.append((method, data))
        return {"response": 1}


async def test_wrapped_request_marks_peer_as_answered() -> None:
    api = FakeApi()
    silent_guard.install(api)
    started = time.monotonic()
    assert not silent_guard.answered_since(4242, started)
    await api.request("messages.send", {"peer_id": 4242, "message": "x"})
    assert silent_guard.answered_since(4242, started)
    assert api.calls == [("messages.send", {"peer_id": 4242, "message": "x"})]  # вызов дошёл как есть


async def test_broadcast_peer_ids_are_marked_too() -> None:
    api = FakeApi()
    silent_guard.install(api)
    started = time.monotonic()
    await api.request("messages.send", {"peer_ids": "11,12", "message": "x"})
    assert silent_guard.answered_since(11, started) and silent_guard.answered_since(12, started)


async def test_unanswered_message_gets_fresh_keyboard(monkeypatch) -> None:
    api = FakeApi()
    silent_guard.install(api)
    sent = []

    class Messages:
        async def send(self, **kw):
            sent.append(kw)

    api.messages = Messages()
    monkeypatch.setattr(silent_guard, "GRACE_SECONDS", 0)

    from bot import battle_keyboard
    from bot.handlers import world

    monkeypatch.setattr(battle_keyboard, "active_battle_keyboard", lambda peer: None)

    async def fake_keyboard(db, character, peer_id, now):
        return "KB"

    monkeypatch.setattr(world, "_current_keyboard", fake_keyboard)

    class Char:
        creation_state = None

    async def fake_get_character(db, vk_id):
        return Char()

    import services.onboarding_service as onb

    monkeypatch.setattr(onb, "get_character", fake_get_character)

    class FakeSession:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    import services.db as dbmod

    monkeypatch.setattr(dbmod, "get_session_factory", lambda: (lambda: FakeSession()))

    await silent_guard._check_later(777, 777, time.monotonic())
    assert sent and sent[0]["keyboard"] == "KB" and sent[0]["message"] == silent_guard.STALE_TEXT

    # Ответ был - страховка молчит.
    sent.clear()
    started = time.monotonic()
    await api.request("messages.send", {"peer_id": 778})
    await silent_guard._check_later(778, 778, started)
    assert sent == []
