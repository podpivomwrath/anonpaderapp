"""У Монолита (5 бросков) победа без трофеев - редкость (~0.3%). Жалоба
2026-10-17: у thefatherdjun 5 пустых побед из 122 на клетке (0;0)."""

import random

from services import encounter_service


async def test_monolith_kill_almost_never_empty(db_session, make_character):
    hero = await make_character(level=60)
    hero.pos_x, hero.pos_y = 0, 0
    rng = random.Random(11)
    empty = 0
    runs = 400
    for _ in range(runs):
        outcome = await encounter_service.resolve_victory(db_session, hero, 60, rng, None)
        if not outcome.trophies_gained:
            empty += 1
    assert empty / runs < 0.02, empty
