"""Патч 37: rebuild() каждого модуля восстанавливает клавиатуру ТЕКУЩЕГО
экрана (для /клавиатура и после рестарта бота) — см.
bot/handlers/world.py::_screen_keyboard/_current_keyboard."""

import json

import bot.handlers.appraiser as appraiser_handlers
import bot.handlers.combat as combat_handlers
import bot.handlers.elixir_shop as elixir_shop_handlers
import bot.handlers.inventory as inventory_handlers
import bot.handlers.world as world_handlers


async def test_appraiser_rebuild_none_for_foreign_screen(db_session, character_at) -> None:
    character = await character_at(50, 50)
    character.screen = "elixir_shop"
    assert await appraiser_handlers.rebuild(db_session, character) is None


async def test_appraiser_rebuild_covers_all_four_screens(db_session, character_at) -> None:
    character = await character_at(50, 50)
    for screen in ("appraiser", "appraiser_trophies", "appraiser_gear", "appraiser_gear_detail"):
        character.screen = screen
        result = await appraiser_handlers.rebuild(db_session, character)
        assert result is not None
        text, kb_json = result
        assert isinstance(text, str) and text
        assert json.loads(kb_json)["inline"] is False


async def test_elixir_shop_rebuild_only_for_own_screen(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await elixir_shop_handlers.rebuild(db_session, character) is None

    character.screen = "elixir_shop"
    result = await elixir_shop_handlers.rebuild(db_session, character)
    assert result is not None
    text, kb_json = result
    assert isinstance(text, str) and text
    assert json.loads(kb_json)["inline"] is False


async def test_inventory_rebuild_only_for_own_screen(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await inventory_handlers.rebuild(db_session, character) is None

    character.screen = "inventory"
    result = await inventory_handlers.rebuild(db_session, character)
    assert result is not None
    text, kb_json = result
    assert isinstance(text, str) and text
    assert json.loads(kb_json)["inline"] is False


async def test_world_screen_keyboard_dispatches_to_owning_module(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await world_handlers._screen_keyboard(db_session, character) is None

    character.screen = "appraiser"
    kb = await world_handlers._screen_keyboard(db_session, character)
    assert kb is not None
    assert json.loads(kb)["inline"] is False

    character.screen = "inventory"
    kb = await world_handlers._screen_keyboard(db_session, character)
    assert kb is not None


async def test_force_unstick_resets_screen_to_root(db_session, character_at, monkeypatch) -> None:
    """combat_handlers.has_active_encounter reads a module-level PvE engine
    (None outside a running bot process) — stub it so force_unstick's
    unconditional encounter check doesn't blow up in isolation."""
    class _FakeEngine:
        sessions: dict = {}

    monkeypatch.setattr(combat_handlers, "_engine", _FakeEngine())

    character = await character_at(50, 50)
    character.screen = "appraiser_gear"
    await world_handlers.force_unstick(db_session, character, peer_id=999999)
    assert character.screen is None
