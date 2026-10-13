"""Облегчение прогрессии и опыт разломов (2026-10-13)."""

import random

from game.combat import balance_config as bc
from models import CharacterStats
from services import experience_service, raid_combat_service


async def _stats(db_session, character):
    from sqlalchemy import select

    return await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))


async def test_game_xp_is_boosted_but_manual_grants_are_exact(db_session, make_character, monkeypatch) -> None:
    monkeypatch.setattr(bc, "XP_GAIN_MULT", 1.25)
    character = await make_character(level=10)
    stats = await _stats(db_session, character)
    assert experience_service.add_experience(character, stats, 100).xp_awarded == 125
    manual = experience_service.add_experience(character, stats, 100, apply_premium=False, game_gain=False)
    assert manual.xp_awarded == 100
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
