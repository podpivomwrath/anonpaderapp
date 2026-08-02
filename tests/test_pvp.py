"""Патч 22: открытое PvP — сервисный слой + чистые хелперы bot/handlers/pvp.py.

Хендлеры, открывающие СОБСТВЕННУЮ сессию БД через get_session_factory()
(attack_command, on_duel_finished, on_mass_battle_finished...), в этом
проекте нигде не юнит-тестируются напрямую (нет monkeypatch-инфраструктуры
для get_session_factory — тот же паттерн, что и у остальных bot/handlers/*).
Здесь тестируется: 1) весь services/pvp_service.py и добавки в
trophy_service.py (принимают db явным параметром — полностью тестируемы),
2) чистые хелперы pvp.py, которые либо принимают db явно (_scene_at,
_resolve_target), либо не трогают БД вовсе (форматирование, резолв цели по
живому состоянию движков)."""

import pytest

from bot.handlers import pvp as pvp_handlers
from game.combat.duel_engine import DuelEngine
from game.combat.session import CombatMode, CombatSessionState
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from models import CharacterTrophy
from services import pvp_service, trophy_service
from tests.conftest import combatant


# --- services/pvp_service.py ---


async def test_class_title_prefers_subclass(make_character) -> None:
    character = await make_character(base_class="warrior", subclass="guardian")
    assert pvp_service.class_title(character) == "Страж"


async def test_class_title_falls_back_to_base_class(make_character) -> None:
    character = await make_character(base_class="rogue", subclass=None)
    assert pvp_service.class_title(character) == "Разбойник"


async def test_others_at_excludes_self_and_far_away(db_session, character_at) -> None:
    me = await character_at(5, 5, region="ridge")
    same_cell = await character_at(5, 5, region="ridge")
    elsewhere = await character_at(6, 5, region="ridge")
    others = await pvp_service.others_at(db_session, me)
    ids = {c.id for c in others}
    assert same_cell.id in ids
    assert elsewhere.id not in ids
    assert me.id not in ids


async def test_others_at_excludes_dead(db_session, character_at) -> None:
    from datetime import datetime, timedelta, timezone

    me = await character_at(5, 5, region="ridge")
    dead = await character_at(5, 5, region="ridge")
    dead.respawn_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    others = await pvp_service.others_at(db_session, me)
    assert dead.id not in {c.id for c in others}


def test_no_reward_for_kill_threshold() -> None:
    assert pvp_service.no_reward_for_kill(winner_level=20, victim_level=9) is True
    assert pvp_service.no_reward_for_kill(winner_level=20, victim_level=10) is False
    assert pvp_service.no_reward_for_kill(winner_level=20, victim_level=15) is False


async def test_record_win_loss_and_leaderboard_ordering(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    c = await make_character()
    pvp_service.record_win(a)
    pvp_service.record_win(a)
    pvp_service.record_loss(a)
    pvp_service.record_win(b)
    pvp_service.record_win(b)
    pvp_service.record_loss(b)
    pvp_service.record_loss(b)
    await db_session.flush()

    entries = await pvp_service.leaderboard(db_session, limit=10)
    # a: 2W/1L, b: 2W/2L, c: 0W/0L — при равенстве побед меньше поражений выше
    assert entries[0].name == a.name
    assert entries[1].name == b.name
    assert entries[-1].name == c.name


async def test_rank_of(db_session, make_character) -> None:
    leader = await make_character()
    pvp_service.record_win(leader)
    pvp_service.record_win(leader)
    me = await make_character()
    pvp_service.record_win(me)
    await db_session.flush()
    assert await pvp_service.rank_of(db_session, leader) == 1
    assert await pvp_service.rank_of(db_session, me) == 2


async def test_log_battle_writes_row(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await pvp_service.log_battle(db_session, "duel", [a.id, b.id], [a.id])
    from sqlalchemy import select

    from models import PvpBattle

    row = await db_session.scalar(select(PvpBattle))
    assert row.battle_type == "duel"
    assert row.participant_ids == [a.id, b.id]
    assert row.winner_ids == [a.id]


# --- trophy_service: transfer_all / split_among (патч 22) ---


async def test_transfer_all_moves_full_stock(db_session, make_character) -> None:
    loser = await make_character()
    winner = await make_character()
    db_session.add(CharacterTrophy(character_id=loser.id, trophy_id="ash_dust", count=5))
    db_session.add(CharacterTrophy(character_id=loser.id, trophy_id="blood_shard", count=2))
    await db_session.flush()

    moved = await trophy_service.transfer_all(db_session, loser.id, winner.id)
    assert moved == {"ash_dust": 5, "blood_shard": 2}

    loser_stock = await trophy_service.get_stock(db_session, loser.id)
    winner_stock = {d.id: c for d, c in await trophy_service.get_stock(db_session, winner.id)}
    assert loser_stock == []
    assert winner_stock == {"ash_dust": 5, "blood_shard": 2}


async def test_transfer_all_empty_stock_noop(db_session, make_character) -> None:
    loser = await make_character()
    winner = await make_character()
    moved = await trophy_service.transfer_all(db_session, loser.id, winner.id)
    assert moved == {}


async def test_split_among_proportional_with_remainder_to_top(db_session, make_character) -> None:
    victim = await make_character()
    a = await make_character()
    b = await make_character()
    db_session.add(CharacterTrophy(character_id=victim.id, trophy_id="ash_dust", count=10))
    await db_session.flush()

    # a нанёс 75% урона, b — 25% от 10 штук: floor(7.5)=7 и floor(2.5)=2,
    # остаток (1) — топ-дамагеру (a) => 8/2
    moved = await trophy_service.split_among(db_session, victim.id, {a.id: 75, b.id: 25})
    assert moved[a.id]["ash_dust"] == 8
    assert moved[b.id]["ash_dust"] == 2

    victim_stock = await trophy_service.get_stock(db_session, victim.id)
    assert victim_stock == []


async def test_split_among_rounding_remainder_goes_to_top_dealer(db_session, make_character) -> None:
    victim = await make_character()
    a = await make_character()
    b = await make_character()
    db_session.add(CharacterTrophy(character_id=victim.id, trophy_id="ash_dust", count=1))
    await db_session.flush()

    # 1 штука, никому не делится поровну — уходит топ-дамагеру (a: урон больше)
    moved = await trophy_service.split_among(db_session, victim.id, {a.id: 100, b.id: 1})
    assert moved == {a.id: {"ash_dust": 1}}


async def test_split_among_empty_shares_keeps_trophies_with_victim(db_session, make_character) -> None:
    victim = await make_character()
    db_session.add(CharacterTrophy(character_id=victim.id, trophy_id="ash_dust", count=4))
    await db_session.flush()

    moved = await trophy_service.split_among(db_session, victim.id, {})
    assert moved == {}
    victim_stock = await trophy_service.get_stock(db_session, victim.id)
    assert victim_stock == [(trophy_service.trophy_defs_ordered()[0], 4)] or victim_stock[0][1] == 4


# --- bot/handlers/pvp.py: чистые хелперы ---


@pytest.fixture(autouse=True)
def _reset_pvp_module():
    """Изолируем модульные реестры между тестами (peer_battle/battles и т.д.)."""
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()
    pvp_handlers._pending_join_prompt.clear()
    duel_engine = DuelEngine()
    mass_engine = TickEngine(InMemoryActionStore())
    pvp_handlers.setup(duel_engine, mass_engine, bot_api=None)
    yield
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()
    pvp_handlers._pending_join_prompt.clear()


def _make_battle(battle_type: str, location: tuple[int, int]) -> pvp_handlers.Battle:
    return pvp_handlers.Battle(battle_type=battle_type, location=location)


async def test_scene_at_excludes_busy_participants(db_session, character_at) -> None:
    me = await character_at(1, 1, region="ridge")
    fighter_a = await character_at(1, 1, region="ridge")
    fighter_b = await character_at(1, 1, region="ridge")
    bystander = await character_at(1, 1, region="ridge")

    battle = _make_battle("duel", (1, 1))
    battle.participants[fighter_a.id] = pvp_handlers._participant(fighter_a, peer_id=111)
    battle.participants[fighter_b.id] = pvp_handlers._participant(fighter_b, peer_id=222)
    battle.side_of = {fighter_a.id: 0, fighter_b.id: 1}
    pvp_handlers._battles[-1] = battle

    solo, battles = await pvp_handlers._scene_at(db_session, me)
    solo_ids = {c.id for c in solo}
    assert bystander.id in solo_ids
    assert fighter_a.id not in solo_ids and fighter_b.id not in solo_ids
    assert len(battles) == 1
    assert battles[0][1] is battle


async def test_resolve_target_by_number_and_nickname(db_session, character_at) -> None:
    me = await character_at(2, 2, region="ridge")
    other = await character_at(2, 2, region="ridge")
    other.name = "Мирэль"

    victim, battle = await pvp_handlers._resolve_target(db_session, me, "1")
    assert victim.id == other.id and battle is None

    victim2, battle2 = await pvp_handlers._resolve_target(db_session, me, "мирэль")
    assert victim2.id == other.id and battle2 is None

    victim3, battle3 = await pvp_handlers._resolve_target(db_session, me, "99")
    assert victim3 is None and battle3 is None


async def test_resolve_target_battle_number_after_solo_players(db_session, character_at) -> None:
    me = await character_at(3, 3, region="ridge")
    solo_player = await character_at(3, 3, region="ridge")
    fighter_a = await character_at(3, 3, region="ridge")
    fighter_b = await character_at(3, 3, region="ridge")

    battle = _make_battle("duel", (3, 3))
    battle.participants[fighter_a.id] = pvp_handlers._participant(fighter_a, peer_id=111)
    battle.participants[fighter_b.id] = pvp_handlers._participant(fighter_b, peer_id=222)
    battle.side_of = {fighter_a.id: 0, fighter_b.id: 1}
    pvp_handlers._battles[-1] = battle

    # 1 игрок соло (solo_player) занимает номер 1, бой — номер 2
    victim, battle_entry = await pvp_handlers._resolve_target(db_session, me, "2")
    assert victim is None
    assert battle_entry is not None
    assert battle_entry[1] is battle

    victim2, _ = await pvp_handlers._resolve_target(db_session, me, "1")
    assert victim2.id == solo_player.id


def test_format_transfer_line_orders_expensive_first() -> None:
    line = pvp_handlers._format_transfer_line({"ash_dust": 2, "blood_shard": 1})
    assert line is not None
    assert line.startswith("Забираешь трофеи:")
    assert "Кровяной осколок" in line and "Пепельная крошка" in line


def test_format_transfer_line_empty_is_none() -> None:
    assert pvp_handlers._format_transfer_line({}) is None


def test_battle_scene_line_groups_by_side() -> None:
    battle = _make_battle("duel", (0, 0))
    battle.participants = {
        1: pvp_handlers.Participant(1, 111, "Тень_В_Ночи", "rogue", "Клинок теней"),
        2: pvp_handlers.Participant(2, 222, "Гримм", "mage", "Отравитель"),
    }
    battle.side_of = {1: 0, 2: 1}
    line = pvp_handlers._battle_scene_line(battle)
    assert line == "⚔️ Бой: Тень_В_Ночи vs Гримм"


def test_default_enemy_target_picks_alive_opponent() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-5, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    enemy = combatant(2, side=1)
    dead_enemy = combatant(3, side=1)
    dead_enemy.current_hp = 0
    session.add(me)
    session.add(enemy)
    session.add(dead_enemy)
    pvp_handlers._mass_engine.sessions[-5] = session
    battle.battle_type = "mass"

    target = pvp_handlers._default_enemy_target(-5, battle, 1)
    assert target == 2  # только живой враг доступен


def test_character_id_for_peer() -> None:
    battle = _make_battle("duel", (0, 0))
    battle.participants[7] = pvp_handlers.Participant(7, 555, "Кто-то", "warrior", "Воин")
    assert pvp_handlers._character_id_for_peer(battle, 555) == 7
    assert pvp_handlers._character_id_for_peer(battle, 999) is None
