"""Горстка пепла — находка после исследования (патч 25, п.4)."""

import random

from bot import ash_handful_state
from game.economy import ash_config as ac
from services import ash_service, wallet_service
from tests.conftest import NoCritRng


def test_pending_state_lifecycle() -> None:
    peer_id = 999001
    assert not ash_handful_state.is_pending(peer_id)
    ash_handful_state.mark(peer_id)
    assert ash_handful_state.is_pending(peer_id)
    assert ash_handful_state.clear(peer_id) is True
    assert not ash_handful_state.is_pending(peer_id)
    assert ash_handful_state.clear(peer_id) is False  # уже снята — второй раз не сгорает


def test_roll_appears_respects_chance() -> None:
    class AlwaysHigh(random.Random):
        def random(self) -> float:
            return 0.999

    class AlwaysLow(random.Random):
        def random(self) -> float:
            return 0.0

    assert ash_service.roll_appears(AlwaysLow()) is True
    assert ash_service.roll_appears(AlwaysHigh()) is False


async def test_collect_grants_xp_and_trophy(db_session, make_character) -> None:
    character = await make_character(level=10, experience=0)
    from sqlalchemy import select
    from models import CharacterStats

    stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )

    result = await ash_service.collect(db_session, character, stats, NoCritRng())
    assert result.xp > 0
    assert character.experience == result.xp
    assert isinstance(result.trophies, dict)  # 1 бросок таблицы трофеев (может быть и пустым)


async def test_collect_item_only_when_rare_roll_hits(db_session, make_character) -> None:
    from sqlalchemy import select
    from models import CharacterStats

    character = await make_character(level=10)
    stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )

    class NeverRareRng(random.Random):
        def random(self) -> float:
            return 0.999  # никогда не проходит ASH_ITEM_CHANCE (~2%)

        def choice(self, seq):
            return seq[0]

    result = await ash_service.collect(db_session, character, stats, NeverRareRng())
    assert result.item is None

    class AlwaysRareRng(random.Random):
        def random(self) -> float:
            return 0.0  # всегда проходит ASH_ITEM_CHANCE

        def choice(self, seq):
            return seq[0]

    result2 = await ash_service.collect(db_session, character, stats, AlwaysRareRng())
    assert result2.item is not None
