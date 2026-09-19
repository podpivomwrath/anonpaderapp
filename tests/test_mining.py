"""Горное дело (патч 59): контент, формулы, общие жилы, добыча.

Отдельный акцент на том, что у горного дела нет ни одного ограничителя, кроме
времени: руду нельзя продать, носить можно сколько угодно, провалов нет. Всё,
что удерживает его в рамках, — блокировка действий на время добычи, штраф за
глубину и конечность общих жил. Каждое из этих трёх мест проверяется здесь.
"""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.economy import mining
from game.economy import mining_config as mc
from models import CharacterOre, MineVein
from services import mining_service

# Рудник первого кольца (Шлаковая штольня) и рудник у Монолита.
EASY_MINE = "ridge_slag_adit"
DEEP_MINE = "monolith_face"


# --- Контент ------------------------------------------------------------------

def test_every_mine_tier_matches_its_ring() -> None:
    """Тир рудника и кольцо его клетки — одно число. Если разойдутся, правило
    PvP («первые два кольца мирные») начнёт противоречить сложности руды."""
    mismatched = [
        f"{m.id} ({m.x};{m.y}): тир {m.tier}, кольцо {mining.ring_tier(m.x, m.y)}"
        for m in mining.all_mines()
        if m.tier != mining.ring_tier(m.x, m.y)
    ]
    assert not mismatched, "тир рудника не совпал с кольцом:\n" + "\n".join(mismatched)


def test_mines_do_not_share_cells_with_lakes() -> None:
    """Два ремесла на одной клетке подрались бы за экран и за кнопку входа."""
    from game.economy import fishing

    lake_cells = {(lake.x, lake.y) for lake in fishing.all_lakes()}
    clashes = [m.id for m in mining.all_mines() if (m.x, m.y) in lake_cells]
    assert not clashes, f"рудник на клетке озера: {clashes}"


def test_mine_ids_and_coords_are_unique() -> None:
    mines = mining.all_mines()
    assert len({m.id for m in mines}) == len(mines)
    assert len({(m.x, m.y) for m in mines}) == len(mines)


def test_every_ore_in_pools_exists_in_catalog() -> None:
    for tier, pool in mc.MINE_POOLS.items():
        for ore_id in pool:
            assert mining.ore_def(ore_id) is not None, f"тир {tier}: нет в каталоге — {ore_id}"


def test_each_region_has_starter_mines_near_its_city() -> None:
    from game.world import world_config as wc

    for region, (cx, cy) in wc.CITY_COORDS.items():
        near = [
            m for m in mining.all_mines()
            if m.tier == 1 and m.region == region
            and max(abs(m.x - cx), abs(m.y - cy)) <= 12
        ]
        assert len(near) >= 3, f"{region}: рудников рядом с городом — {len(near)}"


def test_every_mine_tier_has_a_required_level_and_pool() -> None:
    """Без записи в любой из таблиц добыча упала бы у игрока, а не на старте."""
    for tier in {m.tier for m in mining.all_mines()}:
        assert tier in mc.MINE_REQUIRED_LEVEL
        assert tier in mc.MINE_POOLS
        assert tier in mc.MINE_GRADE_K


# --- Время: единственный гейт глубины ------------------------------------------

def test_deep_mine_punishes_a_beginner_with_hours() -> None:
    """Запрета лезть в глубокий рудник нет — вместо него время. Новичок у
    Монолита должен копать один кусок около часа-полутора."""
    rng = random.Random(1)
    samples = [mining.roll_dig_seconds(rng, 5, 1) for _ in range(500)]
    assert min(samples) >= 25 * 60
    assert max(samples) <= 95 * 60
    assert 50 * 60 <= sum(samples) / len(samples) <= 70 * 60


def test_level_shortens_the_dig_but_never_trivialises_it() -> None:
    """Пол у ускорения нужен: без него уровень превратил бы добычу в мгновенную
    и убил бы весь смысл «АФК-занятия»."""
    for tier in mc.MINE_REQUIRED_LEVEL:
        assert mining.time_multiplier(tier, 10_000) == mc.TIME_PENALTY_MIN
    assert mining.time_multiplier(5, 1) == mc.TIME_PENALTY_MAX


def test_time_multiplier_never_increases_with_level() -> None:
    for tier in mc.MINE_REQUIRED_LEVEL:
        previous = float("inf")
        for level in range(1, 200, 7):
            current = mining.time_multiplier(tier, level)
            assert current <= previous + 1e-9
            previous = current


def test_event_vein_is_faster_but_poorer_than_a_mine() -> None:
    """Иначе мелкая жила была бы строго хуже рудника, и копать её незачем."""
    rng = random.Random(2)
    vein = sum(mining.roll_dig_seconds(rng, 3, 25, event_vein=True) for _ in range(300))
    mine = sum(mining.roll_dig_seconds(rng, 3, 25, event_vein=False) for _ in range(300))
    assert vein < mine
    assert mining.pool_tier_for(3, True) < 3
    assert mining.grade_k(3, 25, event_vein=True) > mining.grade_k(3, 25, event_vein=False)


# --- Градация -----------------------------------------------------------------

def test_deeper_mines_give_better_grades() -> None:
    rng = random.Random(3)
    rare_share = {}
    for tier in (1, 3, 5):
        good = sum(
            mining.roll_grade(rng, tier, 25)[0] != "common" for _ in range(8000)
        )
        rare_share[tier] = good / 8000
    assert rare_share[1] < rare_share[3] < rare_share[5]


def test_legendary_ore_stays_rare_at_any_level() -> None:
    """Уровень бесконечен, и без пола у него легендарная руда стала бы нормой."""
    rng = random.Random(4)
    legendary = sum(
        mining.roll_grade(rng, 5, 10_000)[0] == "legendary" for _ in range(20000)
    )
    assert legendary / 20000 < 0.05


def test_grade_boundaries_follow_config() -> None:
    for threshold, grade_id, _name in mc.GRADES:
        assert mining.grade_name(grade_id)
    assert mc.GRADES[0][1] == "common"
    assert mc.GRADES[-1][1] == "legendary"


# --- Уровень ------------------------------------------------------------------

def test_mining_level_has_no_ceiling() -> None:
    level, xp, gained = mining.add_mining_xp(1, 0, 50_000_000)
    assert level > 50
    assert 0 <= xp < mining.xp_to_next(level)
    assert gained == level - 1


def test_xp_to_next_grows_strictly() -> None:
    for level in range(1, 300):
        assert mining.xp_to_next(level + 1) > mining.xp_to_next(level)


def test_better_grade_gives_more_xp() -> None:
    previous = 0
    for _threshold, grade_id, _name in mc.GRADES:
        current = mining.dig_xp("brown_iron", grade_id)
        assert current > previous
        previous = current


# --- Мирные рудники -----------------------------------------------------------

def test_safe_mines_are_exactly_first_two_rings() -> None:
    for mine in mining.all_mines():
        assert mining.is_safe_mine(mine.x, mine.y) is (mine.tier <= mc.PVP_SAFE_MAX_MINE_TIER)


def test_plain_cell_is_never_a_safe_mine() -> None:
    assert mining.is_mine(45, 45) is False
    assert mining.is_safe_mine(45, 45) is False


# --- Общие жилы (БД) ----------------------------------------------------------

@pytest.mark.asyncio
async def test_dig_reserves_ore_at_the_start(db_session, make_character) -> None:
    """Руда снимается с жилы В НАЧАЛЕ добычи, а не в конце: иначе двое,
    начавшие одновременно, забрали бы один и тот же последний кусок."""
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=1))
    await db_session.flush()

    mine = mining.mine_by_id(EASY_MINE)
    started = await mining_service.start_dig(db_session, character, mine, random.Random(0))

    assert started is not None
    assert await mining_service.ore_in_mine(db_session, EASY_MINE) == 0


@pytest.mark.asyncio
async def test_two_diggers_cannot_take_the_same_last_ore(
    db_session, make_character
) -> None:
    first = await make_character()
    second = await make_character()
    for char in (first, second):
        char.pos_x, char.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=1))
    await db_session.flush()
    mine = mining.mine_by_id(EASY_MINE)

    a = await mining_service.start_dig(db_session, first, mine, random.Random(0))
    b = await mining_service.start_dig(db_session, second, mine, random.Random(0))

    assert a is not None
    assert b is None, "второй игрок забрал несуществующую руду"


@pytest.mark.asyncio
async def test_empty_mine_refuses_the_dig(db_session, make_character) -> None:
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    mine = mining.mine_by_id(EASY_MINE)

    assert await mining_service.start_dig(db_session, character, mine, random.Random(0)) is None
    assert not mining_service.is_digging(character)


@pytest.mark.asyncio
async def test_spawn_fills_only_non_full_veins(db_session) -> None:
    """Иначе часть бросков уходила бы в уже полные жилы и реальная скорость
    наполнения была бы ниже расчётной."""
    for mine in mining.all_mines():
        db_session.add(MineVein(mine_id=mine.id, ore_count=mc.MINE_ORE_CAP))
    await db_session.flush()

    class _AlwaysSpawn(random.Random):
        def random(self) -> float:
            return 0.0

    assert await mining_service.spawn_ore(db_session, _AlwaysSpawn()) is None
    for mine in mining.all_mines():
        assert await mining_service.ore_in_mine(db_session, mine.id) == mc.MINE_ORE_CAP


@pytest.mark.asyncio
async def test_spawn_respects_the_configured_chance(db_session) -> None:
    class _NeverSpawn(random.Random):
        def random(self) -> float:
            return 0.999

    assert await mining_service.spawn_ore(db_session, _NeverSpawn()) is None


@pytest.mark.asyncio
async def test_spawn_adds_exactly_one_ore(db_session) -> None:
    class _AlwaysSpawn(random.Random):
        def random(self) -> float:
            return 0.0

    mine_id = await mining_service.spawn_ore(db_session, _AlwaysSpawn())
    assert mine_id is not None
    assert await mining_service.ore_in_mine(db_session, mine_id) == 1


# --- Добыча -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finished_dig_puts_ore_in_the_inventory(db_session, make_character) -> None:
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=3))
    await db_session.flush()
    mine = mining.mine_by_id(EASY_MINE)
    await mining_service.start_dig(db_session, character, mine, random.Random(0))

    result = await mining_service.finish_dig(db_session, character, random.Random(5))

    assert result is not None
    assert result.xp > 0
    assert await mining_service.total_ore(db_session, character.id) == 1
    assert not mining_service.is_digging(character)


@pytest.mark.asyncio
async def test_returning_to_the_same_mine_keeps_the_remaining_time(
    db_session, make_character
) -> None:
    """Правило статичных жил: пока не ушёл с клетки, можно вернуться и
    доработать остаток. Новую руду при этом резервировать не надо."""
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=2))
    await db_session.flush()
    mine = mining.mine_by_id(EASY_MINE)

    first = await mining_service.start_dig(db_session, character, mine, random.Random(0))
    left_before = await mining_service.ore_in_mine(db_session, EASY_MINE)
    resumed = await mining_service.start_dig(db_session, character, mine, random.Random(0))

    assert resumed.resumed is True
    assert resumed.ends_at == first.ends_at
    assert await mining_service.ore_in_mine(db_session, EASY_MINE) == left_before


@pytest.mark.asyncio
async def test_leaving_the_cell_zeroes_the_dig(db_session, make_character) -> None:
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=1))
    await db_session.flush()
    mine = mining.mine_by_id(EASY_MINE)
    await mining_service.start_dig(db_session, character, mine, random.Random(0))

    assert mining_service.abandon_if_elsewhere(character) is False
    character.pos_x, character.pos_y = 46, 45  # ушёл на соседнюю клетку
    assert mining_service.abandon_if_elsewhere(character) is True
    assert not mining_service.is_digging(character)


@pytest.mark.asyncio
async def test_event_vein_vanishes_on_any_exit(db_session, make_character) -> None:
    """Мелкая жила не принадлежит карте — возвращаться к ней некуда."""
    character = await make_character()
    character.pos_x, character.pos_y = 20, 20
    await mining_service.start_dig(db_session, character, None, random.Random(0))

    assert mining_service.is_event_vein(character) is True
    assert mining_service.abandon_if_elsewhere(character) is True
    assert not mining_service.is_digging(character)


@pytest.mark.asyncio
async def test_abandoned_dig_does_not_return_ore_to_the_vein(
    db_session, make_character
) -> None:
    """Иначе можно было бы занимать последний кусок рудника и отпускать его,
    когда удобно, бесплатно блокируя остальных."""
    character = await make_character()
    character.pos_x, character.pos_y = 46, 44
    db_session.add(MineVein(mine_id=EASY_MINE, ore_count=1))
    await db_session.flush()
    mine = mining.mine_by_id(EASY_MINE)
    await mining_service.start_dig(db_session, character, mine, random.Random(0))

    mining_service.abandon_dig(character)

    assert await mining_service.ore_in_mine(db_session, EASY_MINE) == 0


@pytest.mark.asyncio
async def test_ore_stacks_by_type_and_grade(db_session, make_character) -> None:
    character = await make_character()
    await mining_service.add_ore(db_session, character.id, "brown_iron", "common", 3)
    await mining_service.add_ore(db_session, character.id, "brown_iron", "common", 2)
    await mining_service.add_ore(db_session, character.id, "brown_iron", "rare", 1)

    rows = await mining_service.get_ore(db_session, character.id)

    assert {(d.id, g): c for d, g, c in rows} == {
        ("brown_iron", "common"): 5,
        ("brown_iron", "rare"): 1,
    }
    assert await mining_service.total_ore(db_session, character.id) == 6


@pytest.mark.asyncio
async def test_ore_has_no_carry_limit(db_session, make_character) -> None:
    """Носить можно сколько угодно — это прямое требование дизайна, и никакой
    кап не должен появиться незаметно."""
    character = await make_character()
    db_session.add(CharacterOre(
        character_id=character.id, ore_id="brown_iron", grade="common", count=100_000
    ))
    await db_session.flush()
    await mining_service.add_ore(db_session, character.id, "brown_iron", "common", 1)

    assert await mining_service.total_ore(db_session, character.id) == 100_001


@pytest.mark.asyncio
async def test_restart_lifts_miners_out_of_the_screen_but_keeps_the_deadline(
    db_session, make_character
) -> None:
    """После рестарта игрока выбрасывает «в хаб», но срок добычи остаётся:
    вернётся на клетку — доработает остаток."""
    character = await make_character()
    character.screen = "mine"
    character.mining_mine_id = EASY_MINE
    character.mining_ends_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()

    await mining_service.release_after_restart(db_session)
    await db_session.refresh(character)

    assert character.screen is None
    assert character.mining_ends_at is not None
    assert character.mining_mine_id == EASY_MINE
