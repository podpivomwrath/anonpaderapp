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
