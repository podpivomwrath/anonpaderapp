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


async def test_collect_grants_xp_and_trophy(db_session, character_at) -> None:
    character = await character_at(50, 50, level=10, experience=0)
    from sqlalchemy import select
    from models import CharacterStats

    stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )

    result = await ash_service.collect(db_session, character, stats, NoCritRng())
    assert result.xp > 0
    assert character.experience == result.xp
    assert isinstance(result.trophies, dict)  # 1 бросок таблицы трофеев (может быть и пустым)


async def test_collect_item_only_when_rare_roll_hits(db_session, character_at) -> None:
    from sqlalchemy import select
    from models import CharacterStats

    character = await character_at(50, 50, level=10)
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


async def test_collect_xp_scales_by_zone_not_player_level(db_session, character_at) -> None:
    """Патч 36: горстка пепла на дальнем (низкоуровневом) кольце даёт меньше
    опыта, чем на клетке ближе к Монолиту — раньше опыт зависел только от
    character.level, зона роли не играла вовсе."""
    from sqlalchemy import select
    from models import CharacterStats
    from game.world import grid
    from services import experience_service

    far_ring = await character_at(50, 50, level=30, experience=0)  # dist 50 → зона 1-15
    near_center = await character_at(2, 2, level=30, experience=0)  # dist 2 → зона 60-60
    far_stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == far_ring.id)
    )
    near_stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == near_center.id)
    )

    far_result = await ash_service.collect(db_session, far_ring, far_stats, NoCritRng())
    near_result = await ash_service.collect(db_session, near_center, near_stats, NoCritRng())

    assert far_result.xp < near_result.xp
    zone_level = grid.mob_level_at(50, 50, 30)
    assert zone_level == 15  # clamp(30, 1, 15)
    assert far_result.xp == experience_service.event_xp(zone_level, 30, ac.EVENT_XP_ASH)
