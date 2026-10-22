"""Мелкая жила из исследования (2026-10-22, баг-репорт): копается один раз,
только на своей клетке и только до следующего исследования."""

from bot import explore_rest, pending_activity


async def test_vein_is_tied_to_its_cell() -> None:
    await pending_activity.offer_vein(901, "abc", (3, 4))
    assert not await pending_activity.take_vein(901, "abc", (3, 5))
    assert await pending_activity.take_vein(901, "abc", (3, 4))
    assert not await pending_activity.take_vein(901, "abc", (3, 4))  # одноразовая


async def test_new_exploration_burns_the_old_vein() -> None:
    await pending_activity.offer_vein(902, "abc", (1, 1))
    await explore_rest.start("explore", 902, 30)
    try:
        assert not await pending_activity.take_vein(902, "abc", (1, 1))
    finally:
        await explore_rest.stop("explore", 902)
