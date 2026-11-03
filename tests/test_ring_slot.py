"""Слот кольца один на все перстни (2026-11-03): надеть, снять, поменять."""

import pytest

from game.economy import craft_gear_config as gc
from services import master_recipe_service, preset_service, resist_service
from services import ring_slot_service as rs


async def test_master_and_unburnt_share_one_finger(db_session, make_character) -> None:
    c = await make_character()
    assert await rs.payload(db_session, c) is None
    assert await rs.give(db_session, c, rs.MASTER) == "worn"
    # Палец занят Перстнем Мастера - Несгоревший падает в сумку.
    assert await resist_service.add_ring(db_session, c) == "bag"
    assert rs.worn(c) == rs.MASTER and not c.resist_ring
    slot = await rs.payload(db_session, c)
    assert slot["worn"]["id"] == rs.MASTER and [r["id"] for r in slot["bag"]] == [rs.UNBURNT]

    # Поменять: Несгоревший на палец, Мастер в сумку и перестаёт действовать.
    await rs.wear(db_session, c, rs.UNBURNT)
    assert rs.worn(c) == rs.UNBURNT and not master_recipe_service.has_ring(c)
    assert master_recipe_service.ring_mult(c) == 1
    mods = await preset_service.resolve_active_modifiers(db_session, c)
    assert mods["resist_crit"] == pytest.approx(0.15)
    slot = await rs.payload(db_session, c)
    assert [r["id"] for r in slot["bag"]] == [rs.MASTER] and slot["bag"][0]["tradable"] is False

    # Снятый Мастер всё равно «есть»: второй раз рецепт не сварить.
    assert await master_recipe_service.owns_ring(db_session, c)

    await rs.remove(db_session, c)
    assert rs.worn(c) is None
    with pytest.raises(rs.RingError):
        await rs.remove(db_session, c)
    await rs.wear(db_session, c, rs.MASTER)
    assert master_recipe_service.ring_mult(c) == gc.RING_MULT
    with pytest.raises(rs.RingError, match="уже"):
        await rs.wear(db_session, c, rs.MASTER)
    with pytest.raises(rs.RingError):
        await rs.wear(db_session, c, "nonsense")
