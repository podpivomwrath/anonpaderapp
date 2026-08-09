"""Патч 37: экран персонажа — клавиатура принадлежит экрану, не сообщению."""

from services import screen_service


def test_parent_of_root_is_none() -> None:
    assert screen_service.parent_of(None) is None


def test_parent_of_known_screens() -> None:
    assert screen_service.parent_of("appraiser") is None
    assert screen_service.parent_of("appraiser_trophies") == "appraiser"
    assert screen_service.parent_of("appraiser_gear") == "appraiser"
    assert screen_service.parent_of("appraiser_gear_detail") == "appraiser_gear"
    assert screen_service.parent_of("elixir_shop") is None
    assert screen_service.parent_of("inventory") is None


def test_parent_of_unknown_screen_is_root() -> None:
    assert screen_service.parent_of("some_future_screen") is None


async def test_set_screen_persists_on_character(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert character.screen is None

    await screen_service.set_screen(db_session, character, "appraiser")
    assert character.screen == "appraiser"

    await screen_service.set_screen(db_session, character, None)
    assert character.screen is None
