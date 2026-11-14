"""«Без оповещений» (2026-11-09, репорт 340): переключатель в ui_flags и
отсев получателей рассылок."""

from bot import notices
from bot.miniapp_api import UI_FLAGS


def test_flag_is_allowed_from_miniapp() -> None:
    assert UI_FLAGS["no_notices"] is bool


def test_keep_drops_quiet_players() -> None:
    notices.set_quiet(111, True)
    try:
        assert notices.quiet(111) and not notices.quiet(222)
        assert notices.keep([111, 222, "333"]) == [222, "333"]
    finally:
        notices.set_quiet(111, False)
    assert notices.keep([111]) == [111]


async def test_load_reads_ui_flags(db_session, make_character) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from models import User

    c = await make_character()
    c.ui_flags = {"no_notices": True}
    await db_session.commit()
    vk_id = (await db_session.get(User, c.user_id)).vk_id
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    try:
        assert await notices.load(factory) >= 1
        assert notices.quiet(vk_id)
    finally:
        notices.set_quiet(vk_id, False)


async def test_refused_peer_is_skipped_until_they_write() -> None:
    """Отказ VK (901) - оповещения не шлём, пока игрок сам не напишет (2026-11-13)."""
    from bot import silent_guard

    class RefusingApi:
        async def request(self, method, data, version=None):
            from vkbottle.exception_factory.base_exceptions import VKAPIError

            raise VKAPIError[901](error_msg="Can't send messages for users without permission")

    import pytest
    from vkbottle.exception_factory.base_exceptions import VKAPIError

    api = RefusingApi()
    silent_guard.install(api)
    with pytest.raises(VKAPIError):
        await api.request("messages.send", {"peer_id": 9901, "message": "x"})
    try:
        assert notices.quiet(9901) and notices.keep([9901, 9902]) == [9902]
        notices.reachable_again(9901)
        assert not notices.quiet(9901)
    finally:
        notices.reachable_again(9901)


async def test_closed_player_gets_nothing_at_all_and_vk_is_not_called() -> None:
    """2026-11-14, владелец: игрок занёс сообщество в ЧС - не шлём ВООБЩЕ
    ничего, не только оповещения. Обёртка отбивает запрос сама, тем же 901."""
    import pytest
    from vkbottle.exception_factory.base_exceptions import VKAPIError

    from bot import silent_guard

    calls = []

    class Api:
        async def request(self, method, data, version=None):
            calls.append((method, data))
            return 1

    api = Api()
    silent_guard.install(api)
    notices.mark_unreachable(9911)
    try:
        for method in ("messages.send", "messages.edit"):
            with pytest.raises(VKAPIError):
                await api.request(method, {"peer_id": 9911, "message": "ход боя"})
        with pytest.raises(VKAPIError):
            await api.request("messages.send", {"peer_ids": [9911], "message": "ответ"})
        assert calls == []
        # остальным - как обычно
        assert await api.request("messages.send", {"peer_id": 9912, "message": "x"}) == 1
    finally:
        notices.reachable_again(9911)
    assert await api.request("messages.send", {"peer_id": 9911, "message": "x"}) == 1


class _FakeRedis:
    def __init__(self) -> None:
        self.data: set[str] = set()

    async def sadd(self, key, value):
        self.data.add(str(value))

    async def srem(self, key, value):
        self.data.discard(str(value))

    async def smembers(self, key):
        return set(self.data)


async def test_closed_mark_survives_restart_via_redis() -> None:
    """Раньше отметка жила только в памяти: после каждой выкатки рассылки
    снова упирались в отказы VK (2026-11-14)."""
    import asyncio

    redis = _FakeRedis()
    notices.setup(redis)
    try:
        notices.mark_unreachable(9921)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert redis.data == {"9921"}
        notices._unreachable.discard(9921)  # «рестарт»
        assert await notices.load_unreachable() >= 1
        assert notices.unreachable(9921)
        notices.reachable_again(9921)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert redis.data == set()
    finally:
        notices._unreachable.discard(9921)
        notices.setup(None)


async def test_player_message_clears_mark_before_any_reply() -> None:
    from types import SimpleNamespace

    class Labeler:
        def __init__(self) -> None:
            self.middlewares = []
            self.message_view = SimpleNamespace(register_middleware=self.middlewares.append)

        def raw_event(self, *args, **kwargs):
            return lambda fn: fn

    labeler = Labeler()
    bot = SimpleNamespace(labeler=labeler, on=labeler)
    notices.register(bot)
    middleware_cls = labeler.middlewares[0]
    notices.mark_unreachable(9931)
    try:
        event = SimpleNamespace(from_id=9931, peer_id=9931)
        middleware = middleware_cls.__new__(middleware_cls)
        middleware.event = event
        await middleware.pre()
        assert not notices.unreachable(9931)
    finally:
        notices._unreachable.discard(9931)


def test_demo_and_chats_never_get_notices() -> None:
    assert notices.quiet(900000000001)
    assert notices.keep([900000000001, 2_000_000_005, 12345]) == [12345]
