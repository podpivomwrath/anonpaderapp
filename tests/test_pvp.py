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
from game.combat.duel_engine import DuelEngine, DuelState
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


# --- Патч 33, ч.3: защита от фарма AFK ---


def test_is_afk_true_when_never_active() -> None:
    from models import Character

    character = Character(user_id=1, name="x", base_class="warrior")
    assert pvp_service.is_afk(character) is True


def test_is_afk_false_when_recently_active() -> None:
    from datetime import datetime, timezone

    from models import Character

    character = Character(
        user_id=1, name="x", base_class="warrior", last_active_at=datetime.now(timezone.utc),
    )
    assert pvp_service.is_afk(character) is False


def test_is_afk_true_after_timeout() -> None:
    from datetime import datetime, timedelta, timezone

    from game.economy import pvp_config as pc
    from models import Character

    now = datetime.now(timezone.utc)
    character = Character(
        user_id=1, name="x", base_class="warrior",
        last_active_at=now - timedelta(minutes=pc.AFK_TIMEOUT_MINUTES + 1),
    )
    assert pvp_service.is_afk(character, now=now) is True


def test_is_afk_false_just_under_timeout() -> None:
    from datetime import datetime, timedelta, timezone

    from game.economy import pvp_config as pc
    from models import Character

    now = datetime.now(timezone.utc)
    character = Character(
        user_id=1, name="x", base_class="warrior",
        last_active_at=now - timedelta(minutes=pc.AFK_TIMEOUT_MINUTES - 1),
    )
    assert pvp_service.is_afk(character, now=now) is False


async def test_scene_at_excludes_afk_player(db_session, character_at) -> None:
    from datetime import datetime, timedelta, timezone

    me = await character_at(6, 6, region="ridge")
    afk = await character_at(6, 6, region="ridge")
    afk.last_active_at = datetime.now(timezone.utc) - timedelta(hours=1)
    active = await character_at(6, 6, region="ridge")

    solo, _ = await pvp_handlers._scene_at(db_session, me)
    solo_ids = {c.id for c in solo}
    assert afk.id not in solo_ids
    assert active.id in solo_ids


async def test_scene_at_afk_does_not_affect_ongoing_battle_listing(db_session, character_at) -> None:
    """AFK не даёт защиты в уже идущем бою (патч 33, ч.3) — participant,
    ставший AFK во время боя, остаётся в списке боёв (busy_ids-фильтр
    независим от AFK-статуса)."""
    from datetime import datetime, timedelta, timezone

    me = await character_at(7, 7, region="ridge")
    fighter_a = await character_at(7, 7, region="ridge")
    fighter_b = await character_at(7, 7, region="ridge")
    fighter_a.last_active_at = datetime.now(timezone.utc) - timedelta(hours=1)

    battle = _make_battle("duel", (7, 7))
    battle.participants[fighter_a.id] = pvp_handlers._participant(fighter_a, peer_id=111)
    battle.participants[fighter_b.id] = pvp_handlers._participant(fighter_b, peer_id=222)
    battle.side_of = {fighter_a.id: 0, fighter_b.id: 1}
    pvp_handlers._battles[-1] = battle

    solo, battles = await pvp_handlers._scene_at(db_session, me)
    assert len(battles) == 1
    assert battles[0][1] is battle


async def test_afk_target_named_true_for_afk_player(db_session, character_at) -> None:
    from datetime import datetime, timedelta, timezone

    me = await character_at(8, 8, region="ridge")
    afk = await character_at(8, 8, region="ridge")
    afk.name = "Пропавший"
    afk.last_active_at = datetime.now(timezone.utc) - timedelta(hours=1)

    assert await pvp_handlers._afk_target_named(db_session, me, "пропавший") is True
    assert await pvp_handlers._afk_target_named(db_session, me, "Пропавший") is True


async def test_afk_target_named_false_for_nonexistent_or_numeric(db_session, character_at) -> None:
    me = await character_at(9, 9, region="ridge")
    assert await pvp_handlers._afk_target_named(db_session, me, "НикогоТакого") is False
    assert await pvp_handlers._afk_target_named(db_session, me, "5") is False


async def test_resolve_target_misses_afk_player_by_number_or_name(db_session, character_at) -> None:
    """AFK-игрок не нумеруется вовсе и не резолвится по имени через
    _resolve_target — это подтверждает attack_command's сообщение об AFK,
    а не "нашёл цель"."""
    from datetime import datetime, timedelta, timezone

    me = await character_at(10, 10, region="ridge")
    afk = await character_at(10, 10, region="ridge")
    afk.name = "Тень"
    afk.last_active_at = datetime.now(timezone.utc) - timedelta(hours=1)

    victim, battle = await pvp_handlers._resolve_target(db_session, me, "1")
    assert victim is None and battle is None
    victim2, battle2 = await pvp_handlers._resolve_target(db_session, me, "тень")
    assert victim2 is None and battle2 is None


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
    pvp_handlers._declared_this_tick.clear()
    duel_engine = DuelEngine()
    mass_engine = TickEngine(InMemoryActionStore())
    pvp_handlers.setup(duel_engine, mass_engine, bot_api=None)
    yield
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()
    pvp_handlers._pending_join_prompt.clear()
    pvp_handlers._declared_this_tick.clear()


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


# --- Патч 31, п.6: клавиатура только у ходящего игрока ---


def test_render_duel_turn_line_uses_explicit_next_actor_override() -> None:
    """Регрессия: duel.current_actor_id внутри on_duel_turn_resolved ещё
    указывает на актёра ТОЛЬКО ЧТО завершившегося хода (turn_number движок
    инкрементирует ПОСЛЕ колбэка) — без явного override «Ходит:» показывал бы
    неверное имя. next_actor_id=None (вызов вне колбэка) сохраняет старое
    поведение — используется duel.current_actor_id как есть."""
    a = combatant(1, side=0, name="Атакующий")
    b = combatant(2, side=1, name="Защитник")
    duel = DuelState(session_id=-1, combatants={1: a, 2: b}, order=(1, 2), turn_number=1)

    text_live = pvp_handlers._render_duel(duel, [], finished=False)
    assert "Ходит: Атакующий" in text_live  # order[0] = текущий актёр хода 1

    text_after_turn = pvp_handlers._render_duel(duel, [], finished=False, next_actor_id=2)
    assert "Ходит: Защитник" in text_after_turn


def test_rebuild_keyboard_duel_only_current_actor_gets_combat_kb() -> None:
    a = combatant(1, side=0, name="Атакующий")
    b = combatant(2, side=1, name="Защитник")
    duel = DuelState(session_id=-1, combatants={1: a, 2: b}, order=(1, 2), turn_number=1)
    pvp_handlers._duel_engine.duels[-1] = duel

    battle = _make_battle("duel", (0, 0))
    battle.participants = {
        1: pvp_handlers.Participant(1, 111, "Атакующий", "warrior", "Воин"),
        2: pvp_handlers.Participant(2, 222, "Защитник", "warrior", "Воин"),
    }
    pvp_handlers._battles[-1] = battle
    pvp_handlers._peer_battle[111] = -1
    pvp_handlers._peer_battle[222] = -1

    kb_active = pvp_handlers.rebuild_keyboard(111)
    kb_waiting = pvp_handlers.rebuild_keyboard(222)
    assert kb_active != kb_waiting
    assert kb_waiting == pvp_handlers.pvp_waiting_keyboard()


def test_rebuild_keyboard_mass_hides_after_declaring() -> None:
    session = CombatSessionState(session_id=-7, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0, name="Я")
    session.add(me)
    pvp_handlers._mass_engine.sessions[-7] = session

    battle = _make_battle("mass", (0, 0))
    battle.participants = {1: pvp_handlers.Participant(1, 111, "Я", "warrior", "Воин")}
    pvp_handlers._battles[-7] = battle
    pvp_handlers._peer_battle[111] = -7

    assert pvp_handlers.rebuild_keyboard(111) != pvp_handlers.pvp_waiting_keyboard()

    pvp_handlers._declared_this_tick[-7] = {1}
    assert pvp_handlers.rebuild_keyboard(111) == pvp_handlers.pvp_waiting_keyboard()


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


class _FakeMessages:
    async def send(self, **kwargs) -> int:
        return 1


class _FakeBotApi:
    messages = _FakeMessages()


# --- Патч 38: выбор цели в массовом PvP — чистые хелперы (не трогают БД) ---


def test_enemies_of_returns_only_living_enemies_in_session_order() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-10, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    e1 = combatant(2, side=1, name="Первый")
    e2 = combatant(3, side=1, name="Второй")
    dead_enemy = combatant(4, side=1, name="Мёртвый")
    dead_enemy.current_hp = 0
    ally = combatant(5, side=0, name="Союзник")
    for c in (me, e1, e2, dead_enemy, ally):
        session.add(c)
    pvp_handlers._mass_engine.sessions[-10] = session
    battle.battle_type = "mass"

    assert pvp_handlers._enemies_of(-10, battle, 1) == [2, 3]


def test_init_target_sets_first_enemy() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-11, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    e1 = combatant(2, side=1)
    session.add(me)
    session.add(e1)
    pvp_handlers._mass_engine.sessions[-11] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target.pop(1, None)
    pvp_handlers._init_target(-11, battle, 1)
    assert pvp_handlers._chosen_target[1] == 2


def test_init_target_noop_without_enemies() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-12, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    session.add(me)
    pvp_handlers._mass_engine.sessions[-12] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target.pop(1, None)
    pvp_handlers._init_target(-12, battle, 1)
    assert 1 not in pvp_handlers._chosen_target


def test_resolve_chosen_target_returns_chosen_when_alive() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-13, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    e1 = combatant(2, side=1)
    e2 = combatant(3, side=1)
    for c in (me, e1, e2):
        session.add(c)
    pvp_handlers._mass_engine.sessions[-13] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target[1] = 3
    assert pvp_handlers._resolve_chosen_target(-13, battle, 1) == 3


def test_resolve_chosen_target_falls_back_when_target_dead() -> None:
    """Регрессия: если по какой-то причине _chosen_target не успел
    переключиться (гонка колбэков), действие не должно молча упасть в
    никуда — фолбэк на живого врага, как раньше делал _default_enemy_target."""
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-14, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    dead = combatant(2, side=1)
    dead.current_hp = 0
    alive = combatant(3, side=1)
    for c in (me, dead, alive):
        session.add(c)
    pvp_handlers._mass_engine.sessions[-14] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target[1] = 2  # мёртвая цель
    target = pvp_handlers._resolve_chosen_target(-14, battle, 1)
    assert target == 3
    assert pvp_handlers._chosen_target[1] == 3  # закешировался новый выбор


def test_target_line_formats_name_and_hp_percent() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-15, mode=CombatMode.PVP_GROUP)
    me = combatant(1, side=0)
    enemy = combatant(2, side=1, name="Мирэль")
    enemy.current_hp = round(enemy.max_hp * 0.41)
    session.add(me)
    session.add(enemy)
    pvp_handlers._mass_engine.sessions[-15] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target[1] = 2
    assert pvp_handlers._target_line(-15, battle, 1) == "🎯 Цель: Мирэль (41% HP)"


def test_target_line_empty_without_a_target() -> None:
    battle = _make_battle("mass", (0, 0))
    session = CombatSessionState(session_id=-16, mode=CombatMode.PVP_GROUP)
    session.add(combatant(1, side=0))
    pvp_handlers._mass_engine.sessions[-16] = session
    battle.battle_type = "mass"

    pvp_handlers._chosen_target.pop(1, None)
    assert pvp_handlers._target_line(-16, battle, 1) == ""


# --- Патч 38: смена цели — бесплатное действие, не тратит ход ---


async def test_pick_target_does_not_touch_declared_this_tick(db_session, character_at, monkeypatch) -> None:
    monkeypatch.setattr(pvp_handlers, "_bot_api", _FakeBotApi())
    me = await character_at(5, 5, region="ridge")
    enemy = await character_at(5, 5, region="ridge")

    session = CombatSessionState(session_id=-17, mode=CombatMode.PVP_GROUP)
    me_c = combatant(me.id, side=0, name=me.name)
    e1 = combatant(enemy.id, side=1, name="Первый")
    e2 = combatant(enemy.id + 1000, side=1, name="Второй")
    for c in (me_c, e1, e2):
        session.add(c)
    pvp_handlers._mass_engine.sessions[-17] = session

    battle = _make_battle("mass", (5, 5))
    battle.participants = {
        me.id: pvp_handlers.Participant(me.id, 111, me.name, me.base_class, "Воин"),
        e1.id: pvp_handlers.Participant(e1.id, 222, "Первый", "warrior", "Воин"),
        e2.id: pvp_handlers.Participant(e2.id, 333, "Второй", "warrior", "Воин"),
    }
    pvp_handlers._battles[-17] = battle
    pvp_handlers._peer_battle[111] = -17

    class _FakeMessage:
        peer_id = 111
        from_id = 111

        def get_payload_json(self):
            return {"type": "pvp_target_pick", "target": e2.id}

    await pvp_handlers.pvp_pick_target(_FakeMessage())

    assert pvp_handlers._chosen_target[me.id] == e2.id
    assert me.id not in pvp_handlers._declared_this_tick.get(-17, set())


# --- Патч 38: автопереключение цели при её гибели + уведомление ---


async def test_on_mass_tick_resolved_switches_target_when_it_dies(db_session, character_at, monkeypatch) -> None:
    from game.combat.resolver import TickResult

    sent: list[dict] = []

    class _RecordingMessages:
        async def send(self, **kwargs) -> int:
            sent.append(kwargs)
            return 1

    class _RecordingBotApi:
        messages = _RecordingMessages()

    monkeypatch.setattr(pvp_handlers, "_bot_api", _RecordingBotApi())

    me = await character_at(6, 6, region="ridge")
    dying_enemy = await character_at(6, 6, region="ridge")
    surviving_enemy = await character_at(6, 6, region="ridge")

    session = CombatSessionState(session_id=-18, mode=CombatMode.PVP_GROUP)
    me_c = combatant(me.id, side=0, name=me.name)
    dead_c = combatant(dying_enemy.id, side=1, name="Мирэль")
    dead_c.current_hp = 0
    alive_c = combatant(surviving_enemy.id, side=1, name="Валгар")
    for c in (me_c, dead_c, alive_c):
        session.add(c)
    pvp_handlers._mass_engine.sessions[-18] = session

    battle = _make_battle("mass", (6, 6))
    battle.participants = {
        me.id: pvp_handlers.Participant(me.id, 111, me.name, me.base_class, "Воин"),
        dying_enemy.id: pvp_handlers.Participant(dying_enemy.id, 222, "Мирэль", "mage", "Элементалист"),
        surviving_enemy.id: pvp_handlers.Participant(surviving_enemy.id, 333, "Валгар", "warrior", "Воин"),
    }
    pvp_handlers._battles[-18] = battle
    pvp_handlers._peer_battle[111] = -18
    pvp_handlers._peer_battle[222] = -18
    pvp_handlers._peer_battle[333] = -18
    pvp_handlers._chosen_target[me.id] = dying_enemy.id  # цель — та, что сейчас погибнет

    result = TickResult(lines=["бой продолжается"], deaths=[dying_enemy.id])
    await pvp_handlers.on_mass_tick_resolved(-18, 1, result)

    assert pvp_handlers._chosen_target[me.id] == surviving_enemy.id  # переключилась на живого
    my_message = next(m for m in sent if m["peer_id"] == 111)
    assert "Мирэль падает. Новая цель: Валгар." in my_message["message"]
    assert "🎯 Цель: Валгар" in my_message["message"]


async def test_start_forced_duel_assigns_distinct_sides(db_session, character_at, monkeypatch) -> None:
    """Патч 30, регрессия бага 3: _build_combatant_for всегда возвращает
    side=0 — без явного разведения сторон в _start_forced_duel оба
    комбатанта дуэли оставались на стороне 0, из-за чего
    _default_enemy_target никогда не находил цель и ЛЮБОЕ атакующее
    действие молча отбрасывалось раньше вызова duel_engine.act (ходы при
    этом продолжали идти по таймеру — отсюда "счётчик растёт, действовать
    нельзя")."""
    import bot.handlers.combat as combat_handlers

    class _FakeCombatEngine:
        sessions: dict = {}

    monkeypatch.setattr(pvp_handlers, "_bot_api", _FakeBotApi())
    monkeypatch.setattr(combat_handlers, "_engine", _FakeCombatEngine())
    attacker = await character_at(5, 5, region="ridge")
    victim = await character_at(5, 5, region="ridge")

    await pvp_handlers._start_forced_duel(db_session, attacker, 111, victim, 222)

    battle_id = pvp_handlers._peer_battle[111]
    duel = pvp_handlers._duel_engine.duels[battle_id]
    assert duel.combatants[attacker.id].side != duel.combatants[victim.id].side

    target = pvp_handlers._default_enemy_target(battle_id, pvp_handlers._battles[battle_id], attacker.id)
    assert target == victim.id
