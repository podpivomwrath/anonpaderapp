"""Титулы: тиры, меню выбора, носить можно только открытые."""

from services import title_service


def test_tiers() -> None:
    assert title_service.tier_of("chronicler") == "rare"
    assert title_service.tier_of("attentive") == "legendary"
    assert title_service.tier_of(None) is None
    assert set(title_service.TITLE_TIERS) <= set(title_service.TITLE_NAMES)


async def test_menu_sorted_by_tier_and_marks_active(db_session, make_character) -> None:
    c = await make_character()
    await title_service.unlock(db_session, c, "chronicler")
    await title_service.unlock(db_session, c, "attentive")
    await db_session.flush()
    menu = await title_service.menu(db_session, c)
    assert [t["id"] for t in menu] == ["attentive", "chronicler"]
    # первый открытый становится активным сам
    assert [t["active"] for t in menu] == [False, True]


async def test_set_active_only_unlocked(db_session, make_character) -> None:
    c = await make_character()
    await title_service.unlock(db_session, c, "chronicler")
    await db_session.flush()
    assert not await title_service.set_active(db_session, c, "attentive")
    assert not await title_service.set_active(db_session, c, "no_such")
    assert c.active_title_id == "chronicler"
    assert await title_service.set_active(db_session, c, None)
    assert c.active_title_id is None
    assert await title_service.set_active(db_session, c, "chronicler")
    assert c.active_title_id == "chronicler"
