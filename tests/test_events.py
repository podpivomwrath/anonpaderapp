"""События исследования (патч 9, блок 1): контент, взвешенный выбор, исходы."""

import random

from sqlalchemy import select

from game.content_loader import EventOutcome, load_exploration_events
from game.world import events as event_pool
from game.world import world_config as wc
from models import CharacterStats
from services import event_service, experience_service, vitals_service


async def _stats(db_session, character) -> CharacterStats:
    return await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )


class FixedRng(random.Random):
    """rng.random()/uniform() всегда возвращают заданное значение (0..1)."""

    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._value

    def choice(self, seq):
        return seq[0]


# --- контент ---


def test_exploration_events_load() -> None:
    events = load_exploration_events()
    ids = {e.id for e in events}
    assert ids == {"dead_box", "monolith_shard", "wounded_wanderer", "ash_altar"}
    for event in events:
        assert event.title and event.text
        assert len(event.choices) >= 2
        for choice in event.choices:
            assert choice.label
            assert choice.outcomes


def test_event_pool_random_and_lookup() -> None:
    events = event_pool.all_events()
    picked = event_pool.random_event(random.Random(1))
    assert picked in events
    assert event_pool.event_by_id(picked.id) is picked
    assert event_pool.event_by_id("no_such_event") is None


# --- pick_outcome: взвешенный выбор ---


def test_pick_outcome_lowest_roll_picks_first() -> None:
    outcomes = [
        EventOutcome(weight=60, text="a"),
        EventOutcome(weight=40, text="b"),
    ]
    assert event_service.pick_outcome(FixedRng(0.0), outcomes).text == "a"


def test_pick_outcome_high_roll_picks_last() -> None:
    outcomes = [
        EventOutcome(weight=60, text="a"),
        EventOutcome(weight=40, text="b"),
    ]
    # uniform(0, 100) при value=0.99 -> 99, что попадает во второй интервал (60..100)
    assert event_service.pick_outcome(FixedRng(0.99), outcomes).text == "b"


def test_pick_outcome_three_way_split() -> None:
    outcomes = [
        EventOutcome(weight=55, text="help"),
        EventOutcome(weight=30, text="nothing"),
        EventOutcome(weight=15, text="ambush", combat=True),
    ]
    assert event_service.pick_outcome(FixedRng(0.0), outcomes).text == "help"
    assert event_service.pick_outcome(FixedRng(0.60), outcomes).text == "nothing"
    assert event_service.pick_outcome(FixedRng(0.90), outcomes).combat is True


# --- apply_outcome: эффекты ---


async def test_outcome_nothing_returns_text_unchanged(db_session, character_at) -> None:
    character = await character_at(50, 50)
    stats = await _stats(db_session, character)
    outcome = EventOutcome(weight=100, text="Ты не трогаешь чужую смерть.")
    result = await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    assert result.text == "Ты не трогаешь чужую смерть."
    assert result.is_combat is False


async def test_outcome_combat_flag_short_circuits(db_session, character_at) -> None:
    character = await character_at(50, 50)
    stats = await _stats(db_session, character)
    outcome = EventOutcome(weight=100, text="Рана оказывается краской.", combat=True)
    result = await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    assert result.is_combat is True
    assert result.text == "Рана оказывается краской."


async def test_outcome_xp_grants_fraction_of_mob_xp(db_session, character_at) -> None:
    character = await character_at(50, 50, level=5)
    stats = await _stats(db_session, character)
    before = character.experience
    outcome = EventOutcome(weight=100, text="Тепло растекается по венам.", xp=True)
    await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    expected = round(experience_service.xp_per_mob(5) * wc.EVENT_XP_FRACTION)
    assert character.experience == before + expected


async def test_outcome_trophy_grants_and_appends_drop_line(db_session, character_at) -> None:
    character = await character_at(0, 0)  # центр — не важно, событие всегда 1 бросок

    class AlwaysAshRng(random.Random):
        def random(self) -> float:
            return 0.0

    stats = await _stats(db_session, character)
    outcome = EventOutcome(weight=100, text="Замок поддаётся.", trophy=True)
    result = await event_service.apply_outcome(db_session, character, stats, outcome, AlwaysAshRng())
    assert "Замок поддаётся." in result.text
    assert "С твари осыпается: ⚪ Пепельная крошка." in result.text


async def test_outcome_damage_reduces_hp_but_never_kills(db_session, character_at) -> None:
    character = await character_at(50, 50, level=5)
    stats = await _stats(db_session, character)
    max_hp = vitals_service.max_hp(character, stats)
    vitals_service.set_hp(character, stats, 1)  # уже почти мёртв
    outcome = EventOutcome(
        weight=100, text="Сила бьёт в ответ.", damage_min_pct=50, damage_max_pct=50
    )
    await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    assert vitals_service.current_hp(character, stats) == 1  # floor, не 0/смерть
    assert max_hp > 0  # sanity: формула вообще что-то посчитала


async def test_outcome_combines_trophy_and_damage(db_session, character_at) -> None:
    """Пепельный алтарь / Осквернить: трофей гарантированно + урон одновременно."""
    character = await character_at(0, 0)

    class AlwaysAshRng(random.Random):
        def random(self) -> float:
            return 0.0

        def uniform(self, a, b):
            return a

    stats = await _stats(db_session, character)
    full_hp = vitals_service.current_hp(character, stats)
    outcome = EventOutcome(
        weight=100, text="Ты сгребаешь подношения.",
        trophy=True, damage_min_pct=8, damage_max_pct=12,
    )
    result = await event_service.apply_outcome(db_session, character, stats, outcome, AlwaysAshRng())
    assert "С твари осыпается" in result.text
    assert vitals_service.current_hp(character, stats) < full_hp


async def test_outcome_song_is_guaranteed(db_session, character_at) -> None:
    character = await character_at(50, 50)
    stats = await _stats(db_session, character)
    outcome = EventOutcome(weight=100, text="", song=True)
    result = await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    assert result.text  # непустой обрывок Песни


async def test_outcome_flavor_is_guaranteed(db_session, character_at) -> None:
    character = await character_at(50, 50)
    stats = await _stats(db_session, character)
    outcome = EventOutcome(weight=100, text="", flavor=True)
    result = await event_service.apply_outcome(db_session, character, stats, outcome, FixedRng(0.0))
    assert result.text  # непустой (Песнь или замечание)
