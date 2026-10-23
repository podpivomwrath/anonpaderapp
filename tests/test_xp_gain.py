"""Облегчение прогрессии и опыт разломов (2026-10-13)."""

import random

from game.combat import balance_config as bc
from models import CharacterStats
from services import experience_service, raid_combat_service


async def _stats(db_session, character):
    from sqlalchemy import select

    return await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))


async def test_no_hidden_xp_multiplier(db_session, make_character) -> None:
    """2026-10-23: x1.25 вшит в источники - начисление отдаёт ровно то, что
    посчитал источник (без Метки и древа)."""
    character = await make_character(level=10)
    stats = await _stats(db_session, character)
    assert experience_service.add_experience(character, stats, 100).xp_awarded == 100
    # Облегчение - в самой формуле моба: было 15 + 6*L, стало x1.25.
    assert experience_service.xp_per_mob(10) == round((15 + 6 * 10) * 1.25)
    # требования к уровню прежние
    assert experience_service.xp_to_next(10) == int(bc.XP_BASE * 10 ** bc.XP_EXP)


async def test_rift_xp_is_per_member_not_split(db_session, make_character) -> None:
    a = await make_character(level=30)
    b = await make_character(level=30)
    for c in (a, b):
        c.pos_x, c.pos_y = 15, 0
    rewards = await raid_combat_service.reward_mob_kill(db_session, [a, b], 30, random.Random(1), 2, xp_mobs=10)
    one_mob = experience_service.xp_per_mob(30)
    assert all(r.xp_gained == one_mob * 10 for r in rewards)  # босс - как 10 обычных, каждому


async def test_activity_xp(db_session, make_character) -> None:
    """2026-10-13: рыба 0,15 моба, руда - моб, ящик - 0,1 моба своего уровня."""
    c = await make_character(level=10)
    one_mob = experience_service.xp_per_mob(10)
    assert (await experience_service.grant_activity_xp(db_session, c, "ore")).xp_awarded == one_mob
    assert (await experience_service.grant_activity_xp(db_session, c, "fish")).xp_awarded == round(one_mob * 0.15)
    assert (await experience_service.grant_activity_xp(db_session, c, "crate", 5)).xp_awarded == round(one_mob * 0.5)
    assert experience_service.activity_xp_line(
        await experience_service.grant_activity_xp(db_session, c, "ore")
    ).startswith("✨ +")
