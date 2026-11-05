"""Руины культа (2026-11-05): этаж, ходьба, мешок, выход, гибель, изгнание,
перезапуск посреди боя."""

import random

from sqlalchemy import select

from game import ruins as rules
from game.combat.ruins import RoomStage
from game.combat.session import CombatMode, CombatSessionState
from game.economy import ruins_config as rc
from models import CharacterRune, CharacterTrophy, RuinMember
from services import pvp_service, ruins_service


def test_floor_is_connected_and_boss_is_farthest() -> None:
    for seed in range(200):
        layout = rules.generate(random.Random(seed), 1)
        rooms = rules.rooms_of(layout)
        assert rc.ROOMS_MIN <= len(rooms) <= rc.ROOMS_MAX
        dist = rules.distances(set(rooms), layout["start"])
        assert set(dist) == set(rooms), "этаж связный"
        assert dist[layout["boss"]] == max(dist.values()), "босс - дальше всех"
        assert rooms[layout["start"]] == rules.START and rooms[layout["boss"]] == rules.BOSS
        for i in rooms:
            assert set(rules.exits(layout, i).values()) <= set(rooms)


def test_numbers() -> None:
    assert [rc.mob_level(f) for f in (1, 5, 6, 10, 11)] == [61, 61, 62, 62, 63]
    assert [rc.mob_count(n) for n in (1, 2, 3, 4, 5)] == [2, 3, 5, 5, 5]
    assert [rc.rune_dice(f) for f in (1, 10, 11, 50, 51)] == [1, 1, 2, 5, 6]


def _stage(room: str, party: int) -> CombatSessionState:
    layout = rules.generate(random.Random(1), 7)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    RoomStage(22_000_000, layout, room, party).setup(state)
    return state


def test_room_mobs_by_party_and_elite_has_retinue() -> None:
    assert len(_stage(rules.FIGHT, 1).combatants) == 2
    assert len(_stage(rules.FIGHT, 2).combatants) == 3
    assert len(_stage(rules.FIGHT, 4).combatants) == 5
    elite = _stage(rules.ELITE, 1).combatants.values()
    assert len(elite) == 2 and len({c.max_hp for c in elite}) == 2, "элита + свита"
    assert all(c.level == 62 for c in elite), "этаж 7 - 62 уровень"


async def _party(make_character, n: int = 2):
    chars = []
    for _ in range(n):
        c = await make_character(level=60)
        c.pos_x, c.pos_y = rc.ENTRY_CELL
        chars.append(c)
    return chars


async def test_entry_needs_level_and_cell(db_session, make_character) -> None:
    low = await make_character(level=59)
    low.pos_x, low.pos_y = rc.ENTRY_CELL
    assert "60" in ruins_service.entry_refusal([low])
    far = await make_character(level=60)
    far.pos_x, far.pos_y = 5, 5
    assert "Нет на месте" in ruins_service.entry_refusal([far])


async def test_walk_fight_bag_and_exit(db_session, make_character) -> None:
    a, b = await _party(make_character)
    rng = random.Random(3)
    run = await ruins_service.start(db_session, a, [a, b], rng)
    assert {m.character_id for m in await ruins_service.members(db_session, run.id)} == {a.id, b.id}
    # Внутри - на клетке их нет.
    lookers = await make_character(level=60)
    lookers.pos_x, lookers.pos_y = rc.ENTRY_CELL
    await db_session.flush()
    assert await pvp_service.others_at(db_session, lookers) == []

    direction, target = next(iter(rules.exits(run.layout, run.pos).items()))
    try:
        ruins_service.propose(run, b.id, direction, 2)
        raise AssertionError("не лидер")
    except ruins_service.RuinsError:
        pass
    ruins_service.propose(run, a.id, direction, 2)
    ids = [a.id, b.id]
    assert not ruins_service.all_confirmed(run, ids)
    ruins_service.confirm(run, b.id)
    assert ruins_service.all_confirmed(run, ids)
    kind = ruins_service.move(run, target)
    assert run.pos == target and target in run.visited
    if kind in rules.COMBAT_ROOMS:
        assert run.phase == ruins_service.FIGHT

    # Зачистка комнаты босса: b пал - встаёт с 1 HP, в мешках трофеи и руны.
    run.pos = run.layout["boss"]
    run.floor = 30  # 3 кубика
    found = await ruins_service.room_won(db_session, run, {a.id: 500, b.id: 0}, {a.id: 2, b.id: 0},
                                         random.Random(0))
    assert run.phase == ruins_service.CLEARED
    assert found[b.id].get("raised")
    mb = next(m for m in await ruins_service.members(db_session, run.id) if m.character_id == b.id)
    assert mb.hp == rc.RAISE_HP and not mb.dead
    ma = next(m for m in await ruins_service.members(db_session, run.id) if m.character_id == a.id)
    assert ma.bag.get("trophies"), "живой кладёт трофеи"
    assert not (mb.bag or {}).get("trophies"), "павший в бою трофеев не берёт"

    ma.bag = {"runes": {"monolith_mark": 2}, "trophies": dict(ma.bag["trophies"])}
    paid = await ruins_service.exit_run(db_session, run)
    assert run.status == ruins_service.DONE and run.outcome == ruins_service.EXITED
    rune = await db_session.scalar(select(CharacterRune).where(CharacterRune.character_id == a.id))
    assert rune is not None and rune.count == 2
    trophies = (await db_session.scalars(select(CharacterTrophy).where(CharacterTrophy.character_id == a.id))).all()
    assert sum(t.count for t in trophies) == sum(paid[a.id]["trophies"].values())


async def test_next_floor_resets_potions(db_session, make_character) -> None:
    (a,) = await _party(make_character, 1)
    run = await ruins_service.start(db_session, a, [a], random.Random(1))
    run.pos = run.layout["boss"]
    await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 5}, random.Random(1))
    await ruins_service.next_floor(db_session, run, random.Random(2))
    (m,) = await ruins_service.members(db_session, run.id)
    assert run.floor == 2 and run.phase == ruins_service.WALK and m.consumables_used == 0 and m.hp == 100


async def test_wipe_burns_bags(db_session, make_character) -> None:
    a, b = await _party(make_character)
    run = await ruins_service.start(db_session, a, [a, b], random.Random(1))
    for m in await ruins_service.members(db_session, run.id):
        m.bag = {"runes": {"monolith_mark": 1}}
    await ruins_service.wipe(db_session, run)
    rows = (await db_session.scalars(select(RuinMember).where(RuinMember.run_id == run.id))).all()
    assert all(not r.active and r.bag == {} for r in rows)
    assert run.outcome == ruins_service.WIPED
    assert await db_session.scalar(select(CharacterRune).where(CharacterRune.character_id == a.id)) is None


async def test_kick_takes_bag_and_passes_leadership(db_session, make_character) -> None:
    a, b, c = await _party(make_character, 3)
    run = await ruins_service.start(db_session, a, [a, b, c], random.Random(1))
    for m in await ruins_service.members(db_session, run.id):
        m.bag = {"runes": {"monolith_mark": 1}}
    await ruins_service.kick(db_session, run, a.id)
    assert run.leader_id in (b.id, c.id)
    gone = await db_session.scalar(select(RuinMember).where(RuinMember.character_id == a.id))
    assert not gone.active and gone.bag == {} and gone.left_reason == "kicked"
    assert len(await ruins_service.members(db_session, run.id)) == 2


async def test_restart_mid_fight_returns_to_previous_room(db_session, make_character) -> None:
    (a,) = await _party(make_character, 1)
    run = await ruins_service.start(db_session, a, [a], random.Random(5))
    start = run.pos
    _direction, target = next(iter(rules.exits(run.layout, run.pos).items()))
    run.layout = {**run.layout, "rooms": {**run.layout["rooms"], str(target): rules.FIGHT}}
    (m,) = await ruins_service.members(db_session, run.id)
    m.hp = 300
    ruins_service.move(run, target)
    await ruins_service.snapshot_hp(db_session, run)
    m.hp = 10  # бой шёл, потом перезапуск
    await ruins_service.recover(db_session)
    assert run.pos == start and run.phase == ruins_service.WALK and m.hp == 300


# --- Бой комнаты через движок рейдов ---------------------------------------------


class _Api:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.messages = self

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return 1


class _Msg:
    def __init__(self, peer_id: int, payload: dict) -> None:
        self.peer_id = peer_id
        self.from_id = peer_id
        self._payload = payload

    def get_payload_json(self):
        return self._payload

    async def answer(self, text, **kwargs):
        return None


def _member(cid: int):
    from types import SimpleNamespace

    character = SimpleNamespace(id=cid, name=f"Игрок{cid}", base_class="warrior", subclass=None, level=60)
    stats = SimpleNamespace(strength=4000, agility=60, intellect=60, vitality=4000, will=60)
    return SimpleNamespace(character=character, stats=stats, gear_bonus={}, buff_modifiers={}, peer_id=100 + cid)


async def test_room_fight_keeps_hp_and_reports_back(monkeypatch) -> None:
    from bot.handlers import raid_combat
    from bot.handlers import ruins as ruins_handlers
    from game.combat.tick_engine import InMemoryActionStore, TickEngine

    api = _Api()
    engine = TickEngine(
        InMemoryActionStore(),
        on_tick_resolved=raid_combat.on_raid_tick_resolved,
        on_battle_finished=raid_combat.on_raid_battle_finished,
    )
    engine.start()
    raid_combat.setup(engine, api)
    won: dict = {}

    async def fake_won(session_id, battle):
        won["combatants"] = raid_combat.release_ruins_battle(session_id)
        won["run"] = battle.ruin_run_id

    monkeypatch.setattr(ruins_handlers, "on_room_won", fake_won)
    layout = rules.generate(random.Random(2), 1)
    members = [_member(1), _member(2)]
    stage = RoomStage(22_000_000, layout, rules.FIGHT, 2)
    try:
        battle_id = await raid_combat.start_ruins_room(-55, stage, members, {1: 10**9, 2: 0}, {1: 3, 2: 0}, "бой")
        state = engine.sessions[battle_id]
        me, dead = state.combatants[1], state.combatants[2]
        assert me.current_hp == me.max_hp and me.consumables_used == 3, "здоровье не выше максимума, зелья - с этажа"
        assert not dead.alive, "павший раньше лежит"
        for _ in range(60):
            if battle_id not in raid_combat._battles:
                break
            await raid_combat.raid_attack(_Msg(101, {"type": "raid_attack"}))
        left = {c.name: (c.current_hp, c.alive) for c in engine.sessions.get(battle_id, state).combatants.values()}
        assert won.get("run") == -55, f"итог боя ушёл в руины: {left} tick={state.tick_number}"
        assert won["combatants"][1].alive
        assert 101 not in raid_combat._peer_battle and 1 not in raid_combat._character_in_raid
    finally:
        engine.shutdown() if hasattr(engine, "shutdown") else None
        raid_combat.release_ruins_battle(-1)
