"""Пепельный ларец (патч 24): градации, шансы, награды, история."""

import random

from sqlalchemy import select

from game.combat.battle_report import BattleReport
from game.economy import dailies_config as dc
from game.economy import lootbox_config as lc
from models import CharacterDaily, CharacterLootbox
from services import daily_service, lootbox_service, wallet_service
from tests.conftest import NoCritRng


def _report(**kwargs) -> BattleReport:
    base = dict(
        won=True, turns=3, mob_level=1, start_hp_pct=1.0, hp_min_pct=1.0,
        total_damage_taken=0, max_hp=100, only_basic_attack=False, only_skills=True,
    )
    base.update(kwargs)
    return BattleReport(**base)


def test_grade_chances_sum_to_one() -> None:
    grades = lootbox_service.grade_catalog()
    assert {g.id for g in grades} == {"dusty", "dim", "crimson", "searing", "tear"}
    assert abs(sum(g.chance for g in grades) - 1.0) < 1e-9


def test_boost_multiplier_thresholds() -> None:
    assert lc.boost_multiplier(0) == 1.0
    assert lc.boost_multiplier(6) == 1.0
    assert lc.boost_multiplier(7) == 1.3
    assert lc.boost_multiplier(27) == 1.3
    assert lc.boost_multiplier(28) == 1.6
    assert lc.boost_multiplier(111) == 1.6
    assert lc.boost_multiplier(112) == 2.0
    assert lc.boost_multiplier(1000) == 2.0


def test_chances_boost_favors_rare_grades_and_sums_to_one() -> None:
    base = lootbox_service._chances(1)
    boosted = lootbox_service._chances(112)
    assert boosted["crimson"] > base["crimson"]
    assert boosted["searing"] > base["searing"]
    assert boosted["tear"] > base["tear"]
    assert boosted["dusty"] < base["dusty"]
    assert abs(sum(boosted.values()) - 1.0) < 1e-9


async def test_open_chest_tear_grade_deterministic(db_session, make_character) -> None:
    """NoCritRng.random() всегда ~1.0 → uniform(0, total) попадает в последнюю
    (самую редкую) градацию; choice() всегда первый вариант."""
    character = await make_character(level=1)
    rng = NoCritRng()
    result = await lootbox_service.open_chest(db_session, character, daily_streak=1, rng=rng)
    assert result.grade.id == "tear"
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.donate_currency == 250

    rows = (
        await db_session.scalars(
            select(CharacterLootbox).where(CharacterLootbox.character_id == character.id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].grade == "tear"


async def test_open_chest_ranges_are_respected(db_session, make_character) -> None:
    character = await make_character(level=1)
    rng = random.Random(42)
    for _ in range(30):
        result = await lootbox_service.open_chest(db_session, character, daily_streak=1, rng=rng)
        assert result.grade.id in {"dusty", "dim", "crimson", "searing", "tear"}
        assert result.lines  # всегда хоть что-то начислено


async def test_recent_history_and_grade_counts(db_session, make_character) -> None:
    character = await make_character(level=1)
    rng = NoCritRng()  # всегда "tear"
    for _ in range(3):
        await lootbox_service.open_chest(db_session, character, daily_streak=1, rng=rng)

    history = await lootbox_service.recent_history(db_session, character.id, limit=10)
    assert len(history) == 3
    assert all(h.grade == "tear" for h in history)

    counts = await lootbox_service.grade_counts(db_session, character.id)
    assert counts == {"tear": 3}


async def test_daily_streak_completion_grants_exactly_one_chest(db_session, make_character) -> None:
    character = await make_character(level=10)
    row = CharacterDaily(
        character_id=character.id, quest_id="hunt", progress=0, completed=False,
        date=daily_service.today_msk(),
    )
    db_session.add(row)
    target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    row.progress = target - 1
    await db_session.flush()

    result = await daily_service.record_battle(db_session, character, _report(won=True))
    assert character.daily_streak == 1
    assert result.streak_notice is not None
    assert "Пепельный ларец" in result.streak_notice

    rows = (
        await db_session.scalars(
            select(CharacterLootbox).where(CharacterLootbox.character_id == character.id)
        )
    ).all()
    assert len(rows) == 1


async def test_second_completion_same_day_does_not_grant_second_chest(db_session, make_character) -> None:
    character = await make_character(level=10)
    hunt = CharacterDaily(
        character_id=character.id, quest_id="hunt", progress=0, completed=False,
        date=daily_service.today_msk(),
    )
    wanderer = CharacterDaily(
        character_id=character.id, quest_id="wanderer", progress=0, completed=False,
        date=daily_service.today_msk(),
    )
    db_session.add(hunt)
    db_session.add(wanderer)
    hunt.progress = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level) - 1
    wanderer.progress = dc.scaled_target(daily_service.quest_def("wanderer").base_target, character.level) - 1
    await db_session.flush()

    first = await daily_service.record_battle(db_session, character, _report(won=True))
    assert first.streak_notice is not None
    second = await daily_service.record_cell_moved(db_session, character)
    assert second.streak_notice is None  # тот же день — стрик и ларец уже выданы

    rows = (
        await db_session.scalars(
            select(CharacterLootbox).where(CharacterLootbox.character_id == character.id)
        )
    ).all()
    assert len(rows) == 1
