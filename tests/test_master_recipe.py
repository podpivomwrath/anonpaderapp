"""Мастерский рецепт алхимика (2026-10-23, владелец): без подсказок игрокам;
эликсир (постоянная прибавка), перстень (все ремёсла вдвое) и титул."""

import random

import pytest

from game.economy import craft_gear_config as gc
from game.economy import fishing_config as fc
from models import CharacterFish
from services import cooking_service, item_service, master_recipe_service, mining_service, title_service


async def _stock(db, c):
    c.alchemy_level = gc.MASTER_ALCHEMY_LEVEL
    c.star_dust = gc.MASTER_DUST
    await mining_service.add_ore(db, c.id, gc.MASTER_ORE, "common", 1)
    db.add(CharacterFish(character_id=c.id, fish_id=fc.NAMELESS_ID, grade="common", total_grams=5000))
    await cooking_service.add_food(db, c.id, gc.MASTER_DISH, "common", 1)
    await master_recipe_service._add(db, c.id, gc.VIAL_ID)
    await db.flush()


async def test_recipe_appears_only_when_everything_is_there(db_session, make_character) -> None:
    c = await make_character()
    assert not await master_recipe_service.ready(db_session, c)
    await _stock(db_session, c)
    assert await master_recipe_service.ready(db_session, c)
    c.star_dust = gc.MASTER_DUST - 1
    assert not await master_recipe_service.ready(db_session, c)


async def test_brew_gives_ring_draught_and_title_once(db_session, make_character) -> None:
    c = await make_character()
    await _stock(db_session, c)
    await master_recipe_service.brew(db_session, c)
    assert master_recipe_service.has_ring(c) and c.star_dust == 0
    assert await title_service.has_unlocked(db_session, c.id, gc.TITLE_ID)
    assert await master_recipe_service.count_of(db_session, c.id, gc.DRAUGHT_ID) == 1
    assert not await master_recipe_service.ready(db_session, c)  # второй раз - нет
    with pytest.raises(master_recipe_service.MasterError):
        await master_recipe_service.brew(db_session, c)


async def test_draught_raises_all_stats_forever(db_session, make_character) -> None:
    c = await make_character()
    before = await item_service.compute_gear_bonus(db_session, c.id)
    await master_recipe_service._add(db_session, c.id, gc.DRAUGHT_ID)
    await master_recipe_service.drink(db_session, c)
    after = await item_service.compute_gear_bonus(db_session, c.id)
    assert all(after.get(k, 0) > before.get(k, 0) for k in ("str", "agi", "int", "vit", "wil"))
    with pytest.raises(master_recipe_service.MasterError):
        await master_recipe_service.drink(db_session, c)


async def test_ring_doubles_ore(db_session, character_at) -> None:
    from game.economy import mining

    mine = next(m for m in mining.all_mines() if m.tier == 1)
    c = await character_at(mine.x, mine.y)
    c.ring_id = gc.RING_ID
    await mining_service.refill_all_veins(db_session, 10)
    await mining_service.start_dig(db_session, c, mine, random.Random(1))
    result = await mining_service.finish_dig(db_session, c, random.Random(1))
    assert result.count in (2, 4)
