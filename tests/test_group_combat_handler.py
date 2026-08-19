"""Групповой PvE-бой (патч 51, ч.4): bot/handlers/group_combat.py.

Хендлеры, открывающие СОБСТВЕННУЮ сессию БД, здесь не тестируются напрямую
(тот же принцип, что в tests/test_pvp.py) — тестируется постройка боя
(start_group_encounter, чистая функция поверх переданных данных) и чистые
хелперы выбора цели/отрисовки, работающие с состоянием TickEngine напрямую."""

import random

import pytest

from bot.handlers import group_combat as gc
from game.combat.session import CombatMode
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from services import item_service, preset_service


class FakeMessages:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs) -> int:
        self.sent.append(kwargs)
        return 1


class FakeBotApi:
    def __init__(self) -> None:
        self.messages = FakeMessages()


@pytest.fixture(autouse=True)
def _reset_module_state():
    gc._battles.clear()
    gc._peer_battle.clear()
    gc._declared_this_tick.clear()
    gc._chosen_target.clear()
    gc._active_group_ids.clear()
    yield
    gc._battles.clear()
    gc._peer_battle.clear()
    gc._declared_this_tick.clear()
    gc._chosen_target.clear()
    gc._active_group_ids.clear()


@pytest.fixture
def engine() -> TickEngine:
    return TickEngine(InMemoryActionStore(), max_turns=None)


async def _member_inputs(db_session, make_character, count: int, level: int = 10):
    from sqlalchemy import select

    from models import CharacterStats

    inputs = []
    for i in range(count):
        character = await make_character(level=level, region="ridge")
        character.pos_x, character.pos_y = 5, 5
        stats = await db_session.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        gear_bonus = await item_service.compute_gear_bonus(db_session, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db_session, character)
        inputs.append(gc.MemberCombatInput(character, stats, gear_bonus, buff_modifiers, peer_id=1000 + i))
    return inputs


async def test_start_group_encounter_spawns_one_mob_per_member(db_session, make_character, engine) -> None:
    bot_api = FakeBotApi()
    gc.setup(engine, bot_api)
    inputs = await _member_inputs(db_session, make_character, count=3)

    await gc.start_group_encounter(group_id=1, members_input=inputs, region="ridge", dist=45, rng=random.Random(1))

    assert len(gc._battles) == 1
    battle_id, battle = next(iter(gc._battles.items()))
    assert len(battle.mob_ids) == 3
    assert len(battle.participants) == 3
    state = engine.sessions[battle_id]
    assert state.mode == CombatMode.PVE
    assert state.is_raid is True
    # все игроки зарегистрированы под peer_id
    for m in inputs:
        assert gc._peer_battle[m.peer_id] == battle_id
        assert gc._character_id_for_peer(battle, m.peer_id) == m.character.id


async def test_start_group_encounter_initial_target_assigned(db_session, make_character, engine) -> None:
    bot_api = FakeBotApi()
    gc.setup(engine, bot_api)
    inputs = await _member_inputs(db_session, make_character, count=2)

    await gc.start_group_encounter(group_id=1, members_input=inputs, region="ridge", dist=45, rng=random.Random(1))

    for m in inputs:
        assert m.character.id in gc._chosen_target
        target_id = gc._chosen_target[m.character.id]
        assert target_id in next(iter(gc._battles.values())).mob_ids


async def test_enemies_of_lists_only_opposite_side(db_session, make_character, engine) -> None:
    bot_api = FakeBotApi()
    gc.setup(engine, bot_api)
    inputs = await _member_inputs(db_session, make_character, count=2)
    await gc.start_group_encounter(group_id=1, members_input=inputs, region="ridge", dist=45, rng=random.Random(1))

    battle_id, battle = next(iter(gc._battles.items()))
    cid = inputs[0].character.id
    enemies = gc._enemies_of(battle_id, battle, cid)
    assert set(enemies) == battle.mob_ids


async def test_resolve_chosen_target_falls_back_when_target_dead(db_session, make_character, engine) -> None:
    bot_api = FakeBotApi()
    gc.setup(engine, bot_api)
    inputs = await _member_inputs(db_session, make_character, count=1)
    await gc.start_group_encounter(group_id=1, members_input=inputs, region="ridge", dist=45, rng=random.Random(1))

    battle_id, battle = next(iter(gc._battles.items()))
    cid = inputs[0].character.id
    dead_mob_id = gc._chosen_target[cid]
    state = engine.sessions[battle_id]
    state.combatants[dead_mob_id].current_hp = 0

    resolved = gc._resolve_chosen_target(battle_id, battle, cid)
    assert resolved is None or resolved != dead_mob_id


async def test_render_board_shows_both_sides(db_session, make_character, engine) -> None:
    bot_api = FakeBotApi()
    gc.setup(engine, bot_api)
    inputs = await _member_inputs(db_session, make_character, count=2)
    await gc.start_group_encounter(group_id=1, members_input=inputs, region="ridge", dist=45, rng=random.Random(1))

    battle_id = next(iter(gc._battles))
    state = engine.sessions[battle_id]
    text = gc._render_board(state)
    assert "БОЙ" in text
    assert "👥 ВАША СТОРОНА" in text
    assert "💀 ПРОТИВНИК" in text
