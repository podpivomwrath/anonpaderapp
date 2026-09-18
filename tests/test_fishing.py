"""Рыбалка (патч 58): контент, формулы, садок, продажа, PvP-правило.

Отдельный акцент на трёх местах, где ошибка была бы тихой:
  - тир озера обязан совпадать с кольцом своих координат;
  - цена стака обязана равняться сумме цен его рыб (иначе стак начнёт врать);
  - потолка у уровня рыбалки нет, и формулы не должны на него опираться.
"""

import random

import pytest

from game.economy import fishing
from game.economy import fishing_config as fc
from models import CharacterFish
from services import fishing_service

# --- Контент ------------------------------------------------------------------

def test_every_lake_tier_matches_its_ring() -> None:
    """Тир озера и кольцо его клетки — одно и то же число.

    Если они разъедутся, правило PvP («мирные кольца I-II») начнёт
    противоречить сложности рыбы на том же озере.
    """
    mismatched = [
        f"{lake.id} ({lake.x};{lake.y}): тир {lake.tier}, кольцо {fishing.ring_tier(lake.x, lake.y)}"
        for lake in fishing.all_lakes()
        if lake.tier != fishing.ring_tier(lake.x, lake.y)
    ]
    assert not mismatched, "тир озера не совпал с кольцом:\n" + "\n".join(mismatched)


def test_lake_ids_and_coords_are_unique() -> None:
    lakes = fishing.all_lakes()
    assert len({lake.id for lake in lakes}) == len(lakes)
    assert len({(lake.x, lake.y) for lake in lakes}) == len(lakes)


def test_every_fish_in_pools_exists_in_catalog_and_config() -> None:
    """Пул озера не должен ссылаться на несуществующий вид: такой бросок
    уронил бы заброс уже у игрока, а не на старте."""
    for tier, pool in fc.LAKE_POOLS.items():
        for fish_id in pool:
            assert fishing.fish_def(fish_id) is not None, f"тир {tier}: нет в каталоге — {fish_id}"
            assert fish_id in fc.FISH_STATS, f"тир {tier}: нет в FISH_STATS — {fish_id}"


def test_every_catalog_fish_has_stats() -> None:
    for definition in fishing.fish_defs_ordered():
        assert definition.id in fc.FISH_STATS, f"нет чисел для {definition.id}"
        lo, hi, price = fc.FISH_STATS[definition.id]
        assert 0 < lo < hi, f"кривой диапазон веса у {definition.id}"
        assert price > 0


def test_each_region_has_low_level_lakes_near_its_city() -> None:
    """У каждой фракции должны быть свои низкоуровневые озёра в пределах
    быстрой прогулки — иначе рыбалка стартово доступна не всем одинаково."""
    from game.world import world_config as wc

    for region, (cx, cy) in wc.CITY_COORDS.items():
        near = [
            lake for lake in fishing.all_lakes()
            if lake.tier == 1 and lake.region == region
            and max(abs(lake.x - cx), abs(lake.y - cy)) <= 12
        ]
        assert len(near) >= 3, f"{region}: низкоуровневых озёр рядом с городом — {len(near)}"


# --- Вес, градация, цена ------------------------------------------------------

def test_weight_never_leaves_species_range() -> None:
    rng = random.Random(1)
    for fish_id, (lo, hi, _price) in fc.FISH_STATS.items():
        for level in (1, 25, 100, 500):
            for _ in range(200):
                grams, fraction = fishing.roll_weight(rng, fish_id, level)
                assert lo <= grams <= hi, f"{fish_id}: {grams} вне [{lo}; {hi}]"
                assert 0.0 <= fraction <= 1.0


def test_weight_k_never_reaches_one_even_at_absurd_level() -> None:
    """Уровень бесконечен, а кривизна веса обязана упираться в пол: иначе на
    больших уровнях крупная рыба стала бы нормой и градации обесценились."""
    for level in (1, 100, 1000, 10000):
        assert fishing.weight_k(level) >= fc.WEIGHT_K_FLOOR
    assert fishing.weight_k(1) > fishing.weight_k(100) > fishing.weight_k(1000)


def test_grade_boundaries_follow_config() -> None:
    for threshold, grade_id, _name, _mult in fc.GRADES:
        assert fishing.grade_for(threshold)[0] == grade_id
    assert fishing.grade_for(0.0)[0] == "small"
    assert fishing.grade_for(1.0)[0] == "legendary"


def test_stack_price_equals_sum_of_individual_prices() -> None:
    """Ключевое свойство модели садка: рыба стакается СУММАРНЫМ ВЕСОМ, значит
    цена обязана быть линейной по весу. Если сюда когда-нибудь добавят
    нелинейность, стак начнёт считать не то, что реально поймано."""
    fish_id, grade_id = "pale_perch", "common"
    weights = [900, 1100, 1300]
    stacked = fishing.price_of(fish_id, sum(weights), grade_id)
    separate = sum(
        fc.FISH_STATS[fish_id][2] * w / 1000 * fishing.grade_multiplier(grade_id)
        for w in weights
    )
    assert stacked == pytest.approx(round(separate), abs=1)


def test_fraction_of_roundtrips_with_roll_weight() -> None:
    rng = random.Random(7)
    for _ in range(300):
        grams, fraction = fishing.roll_weight(rng, "bone_pike", 40)
        assert fishing.fraction_of("bone_pike", grams) == pytest.approx(fraction, abs=1e-3)


# --- Обрыв лески --------------------------------------------------------------

def test_deep_lake_stays_hard_at_any_level() -> None:
    """Глубокое озеро обязано сопротивляться даже мастеру: иначе доход рыбалки
    обгоняет всю остальную экономику (измерено tools/sim_fishing.py)."""
    for level in (100, 500, 5000):
        chance = fishing.line_break_chance(5, level, 0.5)
        assert chance > 0.30, f"ур.{level}: обрыв на пятом тире всего {chance:.0%}"


def test_beginner_at_deep_lake_almost_always_breaks() -> None:
    assert fishing.line_break_chance(5, 1, 0.8) >= 0.85


def test_break_chance_is_bounded_everywhere() -> None:
    for tier in fc.LINE_BREAK_BASE:
        for level in (1, 50, 1000):
            for fraction in (0.0, 0.5, 1.0):
                chance = fishing.line_break_chance(tier, level, fraction)
                assert fc.LINE_BREAK_MIN <= chance <= fc.LINE_BREAK_MAX


def test_higher_level_never_increases_break_chance() -> None:
    previous = 1.0
    for level in range(1, 200, 7):
        chance = fishing.line_break_chance(3, level, 0.5)
        assert chance <= previous + 1e-9
        previous = chance


# --- Уровень ------------------------------------------------------------------

def test_fishing_level_has_no_ceiling() -> None:
    """В отличие от боевого уровня (MAX_LEVEL=60) потолка нет — проверяем, что
    прибавка опыта не зацикливается и не упирается."""
    level, xp, gained = fishing.add_fishing_xp(1, 0, 10_000_000)
    assert level > 50
    assert 0 <= xp < fishing.xp_to_next(level)
    assert gained == level - 1


def test_xp_to_next_grows_strictly() -> None:
    for level in range(1, 300):
        assert fishing.xp_to_next(level + 1) > fishing.xp_to_next(level)


def test_break_still_gives_some_xp() -> None:
    """Иначе низкий уровень на сложном озере не ловит ничего И не растёт —
    выбраться из ямы было бы нечем."""
    assert fishing.catch_xp("monolith_catfish", 0.5, landed=False) >= 1


# --- Мирные озёра -------------------------------------------------------------

def test_safe_lakes_are_exactly_first_two_rings() -> None:
    for lake in fishing.all_lakes():
        expected = lake.tier <= fc.PVP_SAFE_MAX_LAKE_TIER
        assert fishing.is_safe_lake(lake.x, lake.y) is expected, lake.id


def test_non_lake_cell_is_never_safe() -> None:
    """Мирной клетку делает именно ОЗЕРО, а не кольцо: обычная клетка
    внешнего кольца обязана оставаться боевой."""
    assert fishing.is_lake(45, 45) is False
    assert fishing.is_safe_lake(45, 45) is False


# --- Садок (БД) ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_bag_stacks_by_species_and_grade(db_session, make_character) -> None:
    character = await make_character()
    for grams in (1000, 2000, 3000):
        db_session.add(CharacterFish(
            character_id=character.id, fish_id="pale_perch", grade="common", total_grams=0
        ))
        break
    await db_session.flush()
    row = (await fishing_service.get_bag(db_session, character.id))
    assert row == []  # нулевые стаки не показываются

    await db_session.execute(
        CharacterFish.__table__.update()
        .where(CharacterFish.character_id == character.id)
        .values(total_grams=6000)
    )
    bag = await fishing_service.get_bag(db_session, character.id)
    assert len(bag) == 1
    definition, grade_id, grams = bag[0]
    assert definition.id == "pale_perch"
    assert grade_id == "common"
    assert grams == 6000


@pytest.mark.asyncio
async def test_sell_bag_empties_it_and_pays(db_session, make_character) -> None:
    from services import wallet_service

    character = await make_character()
    db_session.add(CharacterFish(
        character_id=character.id, fish_id="bone_pike", grade="big", total_grams=20000
    ))
    await db_session.flush()

    expected = await fishing_service.bag_value(db_session, character.id, 1.0)
    gold, grams = await fishing_service.sell_bag(db_session, character, 1.0)

    assert gold == expected
    assert grams == 20000
    assert await fishing_service.bag_total_grams(db_session, character.id) == 0
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency >= gold


@pytest.mark.asyncio
async def test_drop_bag_loses_fish_without_transferring(db_session, make_character) -> None:
    """Рыба при поражении в PvP ПРОПАДАЕТ, а не переходит победителю —
    иначе охотиться на рыбаков было бы выгоднее, чем рыбачить."""
    loser = await make_character()
    winner = await make_character()
    db_session.add(CharacterFish(
        character_id=loser.id, fish_id="rusty_tench", grade="common", total_grams=4000
    ))
    await db_session.flush()

    lost = await fishing_service.drop_bag(db_session, loser.id)

    assert lost == 4000
    assert await fishing_service.bag_total_grams(db_session, loser.id) == 0
    assert await fishing_service.bag_total_grams(db_session, winner.id) == 0


@pytest.mark.asyncio
async def test_bag_capacity_blocks_catch_instead_of_dropping_fish(
    db_session, make_character
) -> None:
    """Полный садок НЕ съедает пойманное молча: заброс просто не завершается."""
    character = await make_character()
    character.fishing_level = 1
    capacity = fishing.bag_capacity_grams(character.fishing_level)
    db_session.add(CharacterFish(
        character_id=character.id, fish_id="monolith_catfish", grade="common",
        total_grams=capacity,
    ))
    await db_session.flush()

    character.fishing_pending_fish = "monolith_catfish"
    character.fishing_pending_grams = 20000
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    character.fishing_cast_at = now - timedelta(seconds=10)
    character.fishing_bite_at = now - timedelta(seconds=1)

    lake = fishing.lake_at(1, -2)
    result = await fishing_service.strike(
        db_session, character, lake, random.Random(0), now=now
    )

    assert result.bag_full is True
    assert result.landed is False
    # Снасть осталась заброшенной — игрок идёт продавать и возвращается.
    assert character.fishing_pending_fish == "monolith_catfish"


# --- Сквозной цикл ------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_cycle_cast_strike_catch_sell(db_session, make_character) -> None:
    """Заброс -> поклёвка -> подсечка -> садок -> продажа, на реальных
    функциях. Юнит-тесты выше проверяют куски; здесь важно, что куски
    состыкованы: состояние заброса переживает переход между вызовами, вес и
    градация доезжают до садка, а продажа его опустошает.
    """
    from datetime import datetime, timedelta, timezone

    from services import wallet_service

    character = await make_character()
    character.fishing_level = 60  # обрыв на первом кольце близок к минимуму
    lake = fishing.lake_at(41, -41)
    assert lake is not None and lake.tier == 1

    caught = 0
    now = datetime.now(timezone.utc)
    rng = random.Random(2024)
    for _ in range(60):
        fishing_service.start_cast(character, lake, rng, now=now)
        if character.fishing_pending_fish is None:
            continue  # пустой заброс — бывает, просто пробуем снова
        # Подсекаем внутри окна: сразу после поклёвки.
        strike_at = character.fishing_bite_at + timedelta(seconds=1)
        result = await fishing_service.strike(db_session, character, lake, rng, now=strike_at)
        assert not result.too_early and not result.nothing
        if result.landed:
            caught += 1
            assert result.grams > 0
            assert result.grade_id in {g[1] for g in fc.GRADES}
            assert result.xp > 0
        # После любого исхода снасть свободна.
        assert character.fishing_cast_at is None

    assert caught > 0, "за 60 забросов на лёгком озере не поймано ничего"
    assert character.fishing_level >= 60

    grams = await fishing_service.bag_total_grams(db_session, character.id)
    assert grams > 0

    gold, sold = await fishing_service.sell_bag(db_session, character, 1.0)
    assert sold == grams
    assert gold > 0
    assert await fishing_service.bag_total_grams(db_session, character.id) == 0
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency >= gold


@pytest.mark.asyncio
async def test_striking_before_the_bite_yields_nothing(db_session, make_character) -> None:
    from datetime import datetime, timezone

    character = await make_character()
    lake = fishing.lake_at(41, -41)
    now = datetime.now(timezone.utc)
    rng = random.Random(5)
    for _ in range(40):
        fishing_service.start_cast(character, lake, rng, now=now)
        if character.fishing_pending_fish is not None:
            break
    result = await fishing_service.strike(db_session, character, lake, rng, now=now)
    assert result.too_early is True
    assert result.landed is False
    assert character.fishing_cast_at is None


@pytest.mark.asyncio
async def test_missing_the_window_reads_as_missed_not_as_a_break(
    db_session, make_character
) -> None:
    """Опоздание и обрыв снасти — разные истории для игрока, и текст их
    различает. Если флаг потеряется, опоздание будет выглядеть невезением."""
    from datetime import datetime, timedelta, timezone

    character = await make_character()
    lake = fishing.lake_at(41, -41)
    now = datetime.now(timezone.utc)
    rng = random.Random(11)
    for _ in range(40):
        fishing_service.start_cast(character, lake, rng, now=now)
        if character.fishing_pending_fish is not None:
            break
    too_late = character.fishing_bite_at + timedelta(
        seconds=fc.STRIKE_WINDOW_SECONDS + 1
    )
    result = await fishing_service.strike(db_session, character, lake, rng, now=too_late)
    assert result.broke is True
    assert result.missed is True
