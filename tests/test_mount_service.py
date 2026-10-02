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


# --- Патч 34, ч.3: «Пепельный вестник» — фиксированное время НА ВЕСЬ путь ---


def test_admin_mount_is_service_rarity_with_zero_ambush() -> None:
    from game.economy import mount_config as mc

    d = mount_service.mount_def(mc.ADMIN_MOUNT_ID)
    assert d is not None
    assert d.rarity == "admin"
    assert mount_service.ambush_chance(mc.ADMIN_MOUNT_ID) == 0.0


def test_total_travel_seconds_fixed_for_admin_mount_regardless_of_distance() -> None:
    from game.economy import mount_config as mc

    assert mount_service.total_travel_seconds(mc.ADMIN_MOUNT_ID, cells=1) == 3.0
    assert mount_service.total_travel_seconds(mc.ADMIN_MOUNT_ID, cells=100) == 3.0
    assert mount_service.total_travel_seconds(mc.ADMIN_MOUNT_ID, cells=0) == 3.0


def test_total_travel_seconds_scales_normally_for_regular_mount() -> None:
    assert mount_service.total_travel_seconds("ashen_steed", cells=4) == 28.0


async def test_start_travel_admin_mount_arrives_in_three_seconds_any_distance(
    db_session, character_at,
) -> None:
    from game.economy import mount_config as mc

    character = await character_at(0, 0, level=10)
    travel = await mount_service.start_travel(
        db_session, character, mc.ADMIN_MOUNT_ID, 50, -50, AlwaysAmbush(), now=NOW,
    )
    assert travel.arrives_at == NOW + timedelta(seconds=3.0)
    assert travel.ambush_at is None  # 0% нападение — даже с "всегда роллящим" rng
    assert travel.ambush_done is True


async def test_start_travel_zero_distance_never_ambushes(db_session, character_at) -> None:
    character = await character_at(5, 5, level=10)
    travel = await mount_service.start_travel(
        db_session, character, "ashen_steed", 5, 5, AlwaysAmbush(), now=NOW
    )
    assert travel.ambush_at is None  # cells=0 — нападать негде


# --- Движение по клеткам ---


def test_line_path_steps_to_neighbours_and_ends_at_target() -> None:
    from game.world import grid

    for a, b in [((0, 30), (30, 0)), ((0, 30), (0, -30)), ((-3, 2), (5, -7)), ((4, 4), (4, 5))]:
        path = grid.line_path(*a, *b)
        assert len(path) == grid.cells_between(*a, *b)
        assert path[-1] == b
        prev = a
        for cell in path:
            assert max(abs(cell[0] - prev[0]), abs(cell[1] - prev[1])) == 1
            assert grid.in_bounds(*cell)
            prev = cell


def _build_travel(**overrides) -> MountTravel:
    defaults = dict(
        character_id=1, mount_id="ashen_steed", from_x=0, from_y=0, to_x=10, to_y=0,
        started_at=NOW, arrives_at=NOW + timedelta(seconds=70),
        ambush_at=None, ambush_done=True, status="traveling",
        step_seconds=7.0, cell_index=0, next_cell_at=NOW + timedelta(seconds=7),
    )
    defaults.update(overrides)
    return MountTravel(**defaults)


async def test_start_travel_sets_up_steps(db_session, character_at) -> None:
    character = await character_at(0, 0, level=10)
    travel = await mount_service.start_travel(db_session, character, "ashen_steed", 10, 0, now=NOW)
    assert travel.step_seconds == 7.0 and travel.cell_index == 0
    assert travel.next_cell_at == NOW + timedelta(seconds=7)


async def test_advance_moves_character_cell_by_cell(make_character) -> None:
    character = await make_character(level=10)
    character.pos_x = character.pos_y = 0
    travel = _build_travel()
    step = mount_service.advance(travel, character, NeverAmbush(), now=NOW + timedelta(seconds=15))
    assert step.moved and not step.arrived
    assert travel.cell_index == 2 and (character.pos_x, character.pos_y) == (2, 0)
    assert mount_service.remaining_seconds(travel, now=NOW + timedelta(seconds=15)) == 6 + 7 * 7
    step = mount_service.advance(travel, character, NeverAmbush(), now=NOW + timedelta(seconds=100))
    assert step.arrived and travel.status == "completed" and (character.pos_x, character.pos_y) == (10, 0)


async def test_ambush_stops_on_the_cell_and_resume_continues_from_it(db_session, make_character) -> None:
    character = await make_character(level=10)
    travel = _build_travel(character_id=character.id)
    db_session.add(travel)
    await db_session.flush()
    step = mount_service.advance(travel, character, AlwaysAmbush(), now=NOW + timedelta(seconds=30))
    assert step.ambushed and travel.status == "ambushed"
    assert travel.cell_index == 1 and (character.pos_x, character.pos_y) == (1, 0)
    assert mount_service.frozen_remaining_seconds(travel) == 9 * 7.0
    later = NOW + timedelta(seconds=500)  # бой шёл долго - в счёт дороги не идёт
    await mount_service.resume_travel(db_session, travel, now=later)
    assert travel.status == "traveling"
    assert travel.next_cell_at == later + timedelta(seconds=7)
    assert travel.arrives_at == later + timedelta(seconds=63)


async def test_paused_travel_waits_instead_of_skipping(make_character) -> None:
    character = await make_character(level=10)
    character.pos_x = character.pos_y = 0
    travel = _build_travel()
    at = NOW + timedelta(seconds=60)
    step = mount_service.advance(travel, character, NeverAmbush(), now=at, paused=True)
    assert not step.moved and travel.cell_index == 0
    assert travel.next_cell_at == at + timedelta(seconds=7)


async def test_legacy_travel_without_steps_arrives_by_timer(make_character) -> None:
    character = await make_character(level=10)
    travel = _build_travel(next_cell_at=None, arrives_at=NOW)
    step = mount_service.advance(travel, character, NeverAmbush(), now=NOW + timedelta(seconds=1))
    assert step.arrived and (character.pos_x, character.pos_y) == (10, 0)


def test_ambush_chance_by_ring_and_safe_cells() -> None:
    outer = mount_service.cell_ambush_chance("ashen_steed", 25, 3)
    middle = mount_service.cell_ambush_chance("ashen_steed", 10, 0)
    center = mount_service.cell_ambush_chance("ashen_steed", 1, 0)
    assert 0 < outer < middle < center
    assert mount_service.cell_ambush_chance("ashen_steed", 0, 30) == 0  # город
    assert mount_service.cell_ambush_chance("admin_ashen_herald", 10, 0) == 0
    # через центр к противоположному городу опаснее, чем вдоль края к соседнему
    across = mount_service.trip_ambush_chance("ashen_steed", 0, 30, 0, -30)
    around = mount_service.trip_ambush_chance("ashen_steed", 0, 30, 30, 0)
    assert across > around > 0


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
