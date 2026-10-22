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
    started = time.time()
    assert not silent_guard.answered_since(4242, started)
    await api.request("messages.send", {"peer_id": 4242, "message": "x"})
    assert silent_guard.answered_since(4242, started)
    assert api.calls == [("messages.send", {"peer_id": 4242, "message": "x"})]  # вызов дошёл как есть


async def test_broadcast_peer_ids_are_marked_too() -> None:
    api = FakeApi()
    silent_guard.install(api)
    started = time.time()
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

    await silent_guard._check_later(777, 777, time.time())
    assert sent and sent[0]["keyboard"] == "KB" and sent[0]["message"] == silent_guard.STALE_TEXT

    # Ответ был - страховка молчит.
    sent.clear()
    started = time.time()
    await api.request("messages.send", {"peer_id": 778})
    await silent_guard._check_later(778, 778, started)
    assert sent == []


async def test_start_is_taken_from_message_date_not_from_pre(monkeypatch) -> None:
    """vkbottle вызывает pre и post на разных экземплярах middleware: время из
    pre терялось, и страховка срабатывала после обычных ответов у всех
    (13.10). Начало - дата сообщения ВК."""
    import asyncio
    from types import SimpleNamespace

    seen = []

    async def fake_check(peer_id, from_id, started):
        seen.append(started)

    monkeypatch.setattr(silent_guard, "_check_later", fake_check)
    event = SimpleNamespace(from_id=5, peer_id=5, date=1_700_000_000)
    middleware = silent_guard.SilentGuardMiddleware(event)
    await middleware.post()
    await asyncio.sleep(0)
    assert seen == [1_700_000_000.0]


async def test_unexpected_send_error_is_logged_closed_dm_is_not(monkeypatch) -> None:
    """2026-10-22: битая клавиатура и прочие баги VK тонули в `except: pass` у
    вызова; закрытая личка - ожидаемо, её не пишем."""
    import pytest

    class VkError(Exception):
        def __init__(self, code):
            super().__init__(f"code {code}")
            self.code = code

    class FailingApi:
        def __init__(self, code):
            self.code = code

        async def request(self, method, data, version=None):
            raise VkError(self.code)

    logged = []
    monkeypatch.setattr(silent_guard.logger, "error", lambda *a, **k: logged.append(a))
    for code, expect_log in ((901, False), (911, True)):
        api = FailingApi(code)
        silent_guard.install(api)
        with pytest.raises(VkError):
            await api.request("messages.send", {"peer_id": 1, "message": "x"})
        assert bool(logged) == expect_log
