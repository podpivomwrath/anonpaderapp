"""Владение маунтами и путешествие (патч 25, п.7)."""

import random
from datetime import datetime, timedelta, timezone

from models import MountTravel
from services import mount_service


def test_ashen_steed_is_rare_with_expected_pace() -> None:
    d = mount_service.mount_def("ashen_steed")
    assert d is not None
    assert d.rarity == "rare"
    assert mount_service.seconds_per_cell("ashen_steed") == 7.0
    assert mount_service.ambush_chance("ashen_steed") == 0.20


def test_unknown_mount_falls_back_to_common_pace() -> None:
    assert mount_service.seconds_per_cell("does_not_exist") == 10.0
    assert mount_service.ambush_chance("does_not_exist") == 0.30


async def test_grant_and_owned_mounts(db_session, make_character) -> None:
    character = await make_character(level=10)
    assert await mount_service.has_any_mount(db_session, character.id) is False

    granted = await mount_service.grant(db_session, character, "ashen_steed")
    assert granted is True
    assert await mount_service.has_any_mount(db_session, character.id) is True

    granted_again = await mount_service.grant(db_session, character, "ashen_steed")
    assert granted_again is False  # уже есть — второй раз не начисляется

    owned = await mount_service.owned_mounts(db_session, character.id)
    assert len(owned) == 1
    assert owned[0].mount_id == "ashen_steed"
    assert owned[0].emoji == "🔵"


NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)


class AlwaysAmbush(random.Random):
    def random(self) -> float:
        return 0.0

    def uniform(self, a: float, b: float) -> float:
        return a  # нападение сразу в начале окна (10% пути)


class NeverAmbush(random.Random):
    def random(self) -> float:
        return 0.999


async def test_start_travel_computes_duration_from_rarity_pace(db_session, character_at) -> None:
    character = await character_at(0, 0, level=10)
    travel = await mount_service.start_travel(
        db_session, character, "ashen_steed", 3, 4, NeverAmbush(), now=NOW
    )
    cells = max(abs(3 - 0), abs(4 - 0))  # Чебышёв = 4
    assert travel.arrives_at == NOW + timedelta(seconds=cells * 7.0)
    assert travel.ambush_at is None
    assert travel.ambush_done is True
    assert travel.status == "traveling"


async def test_start_travel_zero_distance_never_ambushes(db_session, character_at) -> None:
    character = await character_at(5, 5, level=10)
    travel = await mount_service.start_travel(
        db_session, character, "ashen_steed", 5, 5, AlwaysAmbush(), now=NOW
    )
    assert travel.ambush_at is None  # cells=0 — нападать негде


async def test_start_travel_ambush_window_between_start_and_arrival(db_session, character_at) -> None:
    character = await character_at(0, 0, level=10)
    travel = await mount_service.start_travel(
        db_session, character, "ashen_steed", 10, 0, AlwaysAmbush(), now=NOW
    )
    assert travel.ambush_at is not None
    assert NOW < travel.ambush_at < travel.arrives_at
    assert travel.ambush_done is False


def _build_travel(**overrides) -> MountTravel:
    defaults = dict(
        character_id=1, mount_id="ashen_steed", from_x=0, from_y=0, to_x=10, to_y=0,
        started_at=NOW, arrives_at=NOW + timedelta(seconds=70),
        ambush_at=NOW + timedelta(seconds=20), ambush_done=False, status="traveling",
    )
    defaults.update(overrides)
    return MountTravel(**defaults)


def test_frozen_remaining_seconds_uses_ambush_window() -> None:
    travel = _build_travel()
    assert mount_service.frozen_remaining_seconds(travel) == 50.0  # 70 - 20


def test_frozen_remaining_seconds_without_ambush_falls_back_to_remaining() -> None:
    travel = _build_travel(ambush_at=None)
    left = mount_service.frozen_remaining_seconds(travel, now=NOW)
    assert left == mount_service.remaining_seconds(travel, now=NOW)


async def test_resume_travel_preserves_remaining_time_from_ambush(db_session) -> None:
    travel = _build_travel(status="ambushed", ambush_done=True)
    db_session.add(travel)
    await db_session.flush()

    resume_at = NOW + timedelta(seconds=500)  # бой шёл долго — не должен влиять на остаток
    await mount_service.resume_travel(db_session, travel, now=resume_at)

    assert travel.status == "traveling"
    assert travel.arrives_at == resume_at + timedelta(seconds=50)  # 70 - 20 сохранено


async def test_cancel_travel_sets_status(db_session) -> None:
    travel = _build_travel()
    db_session.add(travel)
    await db_session.flush()
    await mount_service.cancel_travel(db_session, travel)
    assert travel.status == "cancelled"


async def test_active_travel_finds_traveling_and_ambushed_not_completed(db_session, make_character) -> None:
    character = await make_character(level=10)
    assert await mount_service.active_travel(db_session, character.id) is None

    travel = _build_travel(character_id=character.id, status="traveling")
    db_session.add(travel)
    await db_session.flush()
    assert await mount_service.active_travel(db_session, character.id) is not None

    travel.status = "ambushed"
    await db_session.flush()
    assert await mount_service.active_travel(db_session, character.id) is not None

    travel.status = "completed"
    await db_session.flush()
    assert await mount_service.active_travel(db_session, character.id) is None


async def test_scan_splits_ambushed_arrived_and_still_traveling(db_session, make_character) -> None:
    due_ambush = await make_character(level=10)
    due_arrival = await make_character(level=10)
    still_going = await make_character(level=10)

    db_session.add(_build_travel(
        character_id=due_ambush.id, ambush_done=False, ambush_at=NOW - timedelta(seconds=1),
        arrives_at=NOW + timedelta(seconds=999),
    ))
    db_session.add(_build_travel(
        character_id=due_arrival.id, ambush_at=None, ambush_done=True,
        arrives_at=NOW - timedelta(seconds=1),
    ))
    db_session.add(_build_travel(
        character_id=still_going.id, ambush_at=None, ambush_done=True,
        arrives_at=NOW + timedelta(seconds=999),
    ))
    await db_session.flush()

    # SQLite (тестовая БД) не хранит tzinfo — прочитанные строки возвращаются
    # наивными; сравниваем с наивным "now" той же точки времени (на
    # Postgres в проде datetime(timezone=True) переживает round-trip как есть).
    result = await mount_service.scan(db_session, now=NOW.replace(tzinfo=None))

    assert [t.character_id for t in result.ambushed] == [due_ambush.id]
    assert result.ambushed[0].status == "ambushed"
    assert result.ambushed[0].ambush_done is True

    assert [t.character_id for t in result.arrived] == [due_arrival.id]
    assert result.arrived[0].status == "completed"

    assert [t.character_id for t in result.still_traveling] == [still_going.id]
