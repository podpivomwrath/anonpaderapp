"""Патч 110: события со сценами - контент, расчёты, исходы, следы, эффекты."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.combat import balance_config as bc
from game.world import grid
from game.world import scene_events as se
from game.world.scene_events import Requirement, SceneResult
from models import CharacterEventEffect, CharacterStats, CharacterTrophy, EventTrail
from services import elixir_service, scene_event_service as ses, trophy_service, wallet_service

# --- Контент ----------------------------------------------------------------------


def _results(scene):
    for choice in scene.choices:
        for r in (choice.result, choice.success, choice.failure, *choice.outcomes):
            if r is not None:
                yield r
    for r in (scene.success, scene.failure, scene.timeout):
        if r is not None:
            yield r


def test_content_graph_is_consistent() -> None:
    content = se.content()
    ids = {e.id for e in content.events}
    assert len(ids) == len(content.events)
    for event in content.events:
        assert event.tier in ("medium", "deep", "finale"), event.id
        assert event.start in event.scenes, event.id
        for scene_id, scene in event.scenes.items():
            assert scene.type in ("choice", "push", "timer", "riddle", "dice"), (event.id, scene_id)
            for choice in scene.choices:
                assert len(choice.label) <= 26, choice.label  # + подпись шанса/цены <= 40
                if choice.check:
                    assert choice.check.stat in se.STATS and choice.check.difficulty in se.CHECK_BASE
                    assert choice.success and choice.failure
                for req in (choice.requires, choice.cost):
                    if req and req.base_class:
                        assert req.base_class in bc.PRIMARY_STAT_BY_CLASS
            for result in _results(scene):
                if result.next:
                    assert result.next in event.scenes, (event.id, result.next)
                if result.effect:
                    assert result.effect in content.effects
                if result.trail:
                    assert result.trail in content.trails
            if scene.type == "riddle":
                assert scene.riddles and all(r.a for r in scene.riddles)
            if scene.type == "push":
                assert scene.risks == sorted(scene.risks)
    for kind, trail in content.trails.items():
        finale = se.event_by_id(trail.finale)
        assert finale is not None and finale.tier == "finale", kind


def test_every_trail_can_be_started_from_the_random_pool() -> None:
    started = set()
    for event in se.content().events:
        for scene in event.scenes.values():
            started |= {r.trail for r in _results(scene) if r.trail}
    assert set(se.content().trails) <= started


def test_every_tier_has_events_everywhere() -> None:
    for tier in se.TIERS:
        for ring in range(1, 5):
            assert se.pick_event(random.Random(1), tier, ring, "ridge", 60) is not None, (tier, ring)


# --- Расчёты ----------------------------------------------------------------------


def test_check_chance_follows_build_and_is_clamped() -> None:
    warrior = {"str": 60, "agi": 15, "int": 10, "vit": 30, "wil": 10}
    assert se.check_chance("str", warrior) > se.check_chance("agi", warrior)
    assert se.check_chance("str", warrior, "hard") < se.check_chance("str", warrior, "easy")
    maxed = {"str": 1000, "agi": 0, "int": 0, "vit": 0, "wil": 0}
    assert se.check_chance("str", maxed) == se.CHECK_MAX
    assert se.check_chance("agi", maxed, "hard") == se.CHECK_MIN


def test_push_penalty_grows_with_depth() -> None:
    assert [se.push_penalty(s) for s in (1, 2, 3, 4, 5, 9)] == ["light", "light", "heavy", "heavy", "ruin", "ruin"]


def test_dice_faces_agree_with_outcome() -> None:
    rng = random.Random(3)
    wins = 0
    for _ in range(4000):
        won, mine, theirs = se.roll_dice(rng, 0.47)
        assert (sum(mine) > sum(theirs)) == won
        wins += won
    assert 0.44 < wins / 4000 < 0.50  # в среднем игрок чуть проигрывает


def test_stake_is_read_from_free_text() -> None:
    from bot.handlers.scene_events import parse_stake

    assert parse_stake("250") == 250
    assert parse_stake("1 000 зол") == 1000
    assert parse_stake("ноль") is None
    assert parse_stake("0") is None
    assert parse_stake("9" * 20) is None


def test_dice_scenes_offer_known_currencies() -> None:
    for event in se.content().events:
        for scene in event.scenes.values():
            if scene.type == "dice":
                assert scene.currencies and set(scene.currencies) <= {"gold", "gems"}


def test_riddle_answers() -> None:
    assert se.answer_matches("Тень!", ["тень"])
    assert se.answer_matches("это же тень", ["тень"])
    assert not se.answer_matches("тенёк", ["тень"])
    assert se.answer_matches("Ёлка", ["елка"])


def test_trail_cell_is_near_in_world_and_not_outward() -> None:
    rng = random.Random(5)
    for x, y in [(0, 28), (-20, 3), (5, -5), (29, 0)]:
        for _ in range(30):
            cx, cy = se.pick_trail_cell(rng, x, y)
            assert se.TRAIL_MIN_CELLS <= grid.cells_between(x, y, cx, cy) <= se.TRAIL_MAX_CELLS
            assert grid.in_bounds(cx, cy) and grid.city_region_at(cx, cy) is None
            assert grid.ring_tier(cx, cy) >= grid.ring_tier(x, y)


# --- Исходы -----------------------------------------------------------------------


async def _stats(db, character) -> CharacterStats:
    return await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))


async def test_reward_gives_xp_and_gold_scales_with_ring(db_session, character_at) -> None:
    near = await character_at(0, 28, level=10)
    deep = await character_at(4, 0, level=10)
    assert ses.gold_unit(deep) > ses.gold_unit(near)
    stats = await _stats(db_session, near)
    applied = await ses.apply_result(db_session, near, stats, SceneResult(text="Т", reward=1.0, gold=1.0),
                                     random.Random(1))
    assert near.experience > 0 or near.level > 10
    assert (await wallet_service.get_wallet(db_session, near.id)).farm_currency >= ses.gold_unit(near)
    assert applied.lines[0] == "Т"


async def test_cost_is_charged_and_blocks_when_missing(db_session, character_at) -> None:
    me = await character_at(0, 28, farm=0)
    heal = Requirement(elixir="heal")
    assert not await ses.can_afford(db_session, me, heal)
    await elixir_service.grant(db_session, me.id, "heal_small", 1)
    assert await ses.can_afford(db_session, me, heal)
    assert await ses.pay(db_session, me, heal)
    assert not await ses.can_afford(db_session, me, heal)
    assert not await ses.can_afford(db_session, me, Requirement(gold=1.0))


async def test_ruin_leaves_one_percent_and_burns_trophies(db_session, character_at) -> None:
    me = await character_at(0, 28, level=30)
    await trophy_service.grant_specific(db_session, me.id, "ash_dust", 20)
    stats = await _stats(db_session, me)
    await ses.apply_result(db_session, me, stats, SceneResult(ruin=True), random.Random(2))
    from services import item_service, vitals_service

    vit = (await item_service.compute_gear_bonus(db_session, me.id)).get("vit", 0)
    assert vitals_service.current_hp(me, stats, vit) <= max(1, round(vitals_service.max_hp(me, stats, vit) * 0.01))
    left = await db_session.scalar(select(CharacterTrophy.count).where(CharacterTrophy.character_id == me.id))
    assert left == 14  # 30% из 20 сгорело


async def test_damage_never_kills(db_session, character_at) -> None:
    me = await character_at(0, 28)
    stats = await _stats(db_session, me)
    for _ in range(5):
        await ses.apply_result(db_session, me, stats, SceneResult(damage=[90, 99]), random.Random())
    assert me.respawn_at is None


async def test_effect_modifies_solo_fights_and_ticks_out(db_session, character_at) -> None:
    me = await character_at(0, 28)
    stats = await _stats(db_session, me)
    await ses.apply_result(db_session, me, stats, SceneResult(effect="ash_blessing"), random.Random())
    mods = await ses.solo_modifiers(db_session, me, {"damage_bonus": 0.05})
    assert mods["damage_bonus"] == pytest.approx(0.15)
    fights = se.content().effects["ash_blessing"].fights
    for _ in range(fights - 1):
        assert await ses.tick_effects(db_session, me.id) == []
    assert await ses.tick_effects(db_session, me.id)  # закончился - строка об этом
    assert await db_session.scalar(select(CharacterEventEffect)) is None
    assert await ses.solo_modifiers(db_session, me, {}) == {}


async def test_trail_lifecycle(db_session, character_at) -> None:
    me = await character_at(0, 28)
    stats = await _stats(db_session, me)
    applied = await ses.apply_result(db_session, me, stats, SceneResult(trail="blood"), random.Random(4))
    trail = await db_session.get(EventTrail, me.id)
    assert trail is not None and f"({trail.x}; {trail.y})" in applied.lines[-1]
    assert await ses.take_trail_here(db_session, me) is None  # не та клетка
    assert "Кровавый след" in "\n".join(await ses.summary_lines(db_session, me))
    me.pos_x, me.pos_y = trail.x, trail.y
    assert await ses.take_trail_here(db_session, me) is not None
    assert await db_session.get(EventTrail, me.id) is None


async def test_cold_trail_is_reported_once(db_session, character_at) -> None:
    me = await character_at(0, 28)
    db_session.add(EventTrail(character_id=me.id, kind="cart", x=0, y=25,
                              expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
    await db_session.flush()
    assert any("замело" in line for line in await ses.summary_lines(db_session, me))
    assert await ses.summary_lines(db_session, me) == []
