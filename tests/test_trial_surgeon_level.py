"""Хирург засчитывается как противник 61 уровня для испытаний.

На 60 уровне мобов выше в мире нет, и «Победи того, кто выше тебя уровнем»
(Тёмное вознаграждение и др.) было невыполнимо.
"""

from sqlalchemy import select

from game.economy import raid_config as rc
from models import CharacterUnlockedBuff
from services import trial_service


async def test_surgeon_level_unlocks_higher_level_trial_at_sixty(db_session, make_character) -> None:
    me = await make_character(level=60)
    me.subclass = "dark_mystic"
    await db_session.flush()
    unlocked = await trial_service.record_level_kill(db_session, me, rc.SURGEON_TRIAL_LEVEL)
    assert "dark_mystic_dark_reward" in unlocked
    got = await db_session.scalar(select(CharacterUnlockedBuff.buff_id).where(
        CharacterUnlockedBuff.character_id == me.id, CharacterUnlockedBuff.buff_id == "dark_mystic_dark_reward",
    ))
    assert got == "dark_mystic_dark_reward"


async def test_same_level_does_not_count(db_session, make_character) -> None:
    me = await make_character(level=60)
    me.subclass = "dark_mystic"
    await db_session.flush()
    assert await trial_service.record_level_kill(db_session, me, 60) == []


def test_surgeon_is_above_the_level_cap() -> None:
    from game.combat import balance_config as bc

    assert rc.SURGEON_TRIAL_LEVEL > bc.MAX_LEVEL
