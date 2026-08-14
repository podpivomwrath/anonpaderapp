"""Патч 39: кварталы города — _render_city_screen (общий рендер для входа и
восстановления) + переходы между Площадью/Таверной/Торговым кварталом."""

import json

import bot.handlers.world as world_handlers
from bot.keyboards.world import BTN_MARKET_QUARTER, BTN_SQUARE_BACK, BTN_TAVERN


def _labels(kb_json: str) -> set[str]:
    return {btn["action"]["label"] for row in json.loads(kb_json)["buttons"] for btn in row}


async def test_render_city_screen_none_outside_city(db_session, character_at) -> None:
    character = await character_at(0, 0)  # не город
    assert await world_handlers._render_city_screen(db_session, character, None) is None


async def test_render_city_screen_square_own_city(db_session, character_at) -> None:
    character = await character_at(50, 50, region="ridge")
    text, kb_json = await world_handlers._render_city_screen(db_session, character, None)
    assert text  # атмосферный текст непустой
    labels = _labels(kb_json)
    assert BTN_TAVERN in labels
    assert BTN_MARKET_QUARTER in labels


async def test_render_city_screen_square_foreign_hides_tavern(db_session, character_at) -> None:
    character = await character_at(-50, 50, region="ridge")  # физически в woods, дома в ridge
    text, kb_json = await world_handlers._render_city_screen(db_session, character, None)
    assert "⚠️" in text or "чужие" in text  # текст предупреждает о чужом городе
    labels = _labels(kb_json)
    assert BTN_TAVERN not in labels
    assert BTN_MARKET_QUARTER in labels


async def test_render_city_screen_tavern(db_session, character_at) -> None:
    character = await character_at(50, 50, region="ridge")
    text, kb_json = await world_handlers._render_city_screen(db_session, character, "tavern")
    assert text
    assert "Таверна" in text


async def test_render_city_screen_tavern_foreign_falls_back_to_square(db_session, character_at) -> None:
    """Таверна недоступна в чужом городе — рендер откатывается на площадь,
    а не возвращает пустой/ломаный экран."""
    character = await character_at(-50, 50, region="ridge")
    text, kb_json = await world_handlers._render_city_screen(db_session, character, "tavern")
    labels = _labels(kb_json)
    assert BTN_TAVERN not in labels
    assert BTN_MARKET_QUARTER in labels  # это уже площадь, не таверна


async def test_render_city_screen_market_quarter_own_city(db_session, character_at) -> None:
    character = await character_at(50, 50, region="ridge")
    text, kb_json = await world_handlers._render_city_screen(db_session, character, "market_quarter")
    assert "Торговый квартал" in text
    assert BTN_SQUARE_BACK in _labels(kb_json)


async def test_render_city_screen_market_quarter_foreign_warns_in_text(db_session, character_at) -> None:
    character = await character_at(-50, 50, region="ridge")
    text, _ = await world_handlers._render_city_screen(db_session, character, "market_quarter")
    assert "наценк" in text or "чужой" in text.lower()
