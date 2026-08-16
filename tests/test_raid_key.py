"""Ключ Монолита (патч 45, ч.4): дроп-шанс, кап, тишина на капе."""

import random

from game.economy import raid_key_config as rc
from services import raid_key_service


class FixedRng(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def random(self) -> float:
        return self._value


async def test_maybe_grant_below_threshold_grants_key(db_session, make_character) -> None:
    character = await make_character(level=10)
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is True
    assert character.raid_keys == 1


async def test_maybe_grant_above_threshold_no_key(db_session, make_character) -> None:
    character = await make_character(level=10)
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.999))
    assert dropped is False
    assert character.raid_keys == 0


async def test_maybe_grant_respects_cap(db_session, make_character) -> None:
    character = await make_character(level=10)
    character.raid_keys = rc.RAID_KEY_CAP
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is False
    assert character.raid_keys == rc.RAID_KEY_CAP
