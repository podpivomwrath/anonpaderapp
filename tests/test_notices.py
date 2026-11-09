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
