"""Рейд «Тропа Безымянного» (2026-10-20): лабиринт и бой на арене 3×3."""

import json
import random
from collections import deque
from types import SimpleNamespace

from game import raid_trail as lab_rules
from game.combat import raid_trail as trail
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.economy import raid_trail_config as tc
from tests.conftest import combatant


# --- Лабиринт ---------------------------------------------------------------------


def _path(lab: lab_rules.Labyrinth, start: int, goal: int) -> list[int]:
    """Клетки от start до goal по открытым проходам (без стартовой)."""
    prev = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        for n in lab_rules.neighbors(cur).values():
            if n not in prev and lab.maze.connected(cur, n, lab.grate_open):
                prev[n] = cur
                queue.append(n)
    out, cur = [], goal
    while cur != start:
        out.append(cur)
        cur = prev[cur]
    return out[::-1]


def _calm(lab: lab_rules.Labyrinth) -> None:
    """Убрать с пути всё, что отбрасывает назад: ямы и Безымянного."""
    for i, k in list(lab.maze.kinds.items()):
        if k == lab_rules.PIT:
            del lab.maze.kinds[i]
    lab.hunter = -1
    lab.hunter_next = 10**9


def _walk(lab, cid, goal, now):
    t = now
    for cell in _path(lab, lab.pos[cid], goal):
        assert lab.move(cid, cell, t).ok
        t += tc.STEP_SECONDS
    return t


def test_walls_and_adjacency_are_enforced() -> None:
    lab = lab_rules.Labyrinth([1], random.Random(3))
    _calm(lab)
    here = lab.pos[1]
    for d, n in lab_rules.neighbors(here).items():
        res = lab.move(1, n, 0.0)
        if d in lab.exits(here):
            assert res.ok
            lab.pos[1] = here
        else:
            assert not res.ok and res.reason in ("wall", "grate")
    assert lab.move(1, lab_rules.GATE, 0.0).reason == "not_adjacent"


def test_start_always_has_two_open_exits() -> None:
    """Репорт 2026-10-21: с одним ходом Безымянный запер группу на входе."""
    for seed in range(300):
        lab = lab_rules.Labyrinth([1], random.Random(seed))
        assert len(lab.exits(lab_rules.START)) == 2, seed
        assert not set(lab_rules.neighbors(lab_rules.START).values()) & lab.maze.locked, seed


def test_solo_run_can_finish_with_plate_hold() -> None:
    """Соло: плита держит решётку, пока бежишь до второй; три Следа - ворота."""
    for seed in range(30):
        lab = lab_rules.Labyrinth([1], random.Random(seed))
        _calm(lab)
        t = 0.0
        plates = [i for i, k in lab.maze.kinds.items() if k == lab_rules.PLATE]
        t = _walk(lab, 1, plates[0], t)
        # До второй плиты - с задержкой VK на каждом шаге: удержания должно хватить.
        for cell in _path(lab, lab.pos[1], plates[1]):
            t += 1.5
            assert lab.move(1, cell, t).ok
            t += tc.STEP_SECONDS
        assert lab.grate_open, seed
        for fp in lab.footprints_left():
            t = _walk(lab, 1, fp, t)
        assert not lab.footprints_left()
        t = _walk(lab, 1, lab_rules.GATE, t)
        assert lab.done(t), seed


def test_grate_needs_both_plates_together_in_group() -> None:
    lab = lab_rules.Labyrinth([1, 2], random.Random(5))
    _calm(lab)
    a, b = [i for i, k in lab.maze.kinds.items() if k == lab_rules.PLATE]
    lab.pos[1] = a
    assert not lab.update_plates(0.0)
    lab.pos[1] = lab_rules.START
    lab.pos[2] = b
    assert not lab.update_plates(0.0 + tc.PLATE_HOLD_GROUP + 1)  # первую уже отпустили
    lab.pos[1] = a
    assert lab.update_plates(0.0 + tc.PLATE_HOLD_GROUP + 2)


def test_pit_rest_and_echo() -> None:
    lab = lab_rules.Labyrinth([1], random.Random(7))
    lab.hunter, lab.hunter_next = -1, 10**9
    cells = {k: i for i, k in lab.maze.kinds.items() if k in (lab_rules.PIT, lab_rules.REST, lab_rules.ECHO)}
    for kind, cell in cells.items():
        lab.pos[1] = next(n for n in lab_rules.neighbors(cell).values()
                          if lab.maze.connected(n, cell, True))
        lab.grate_open = True
        res = lab.move(1, cell, 0.0)
        assert res.ok
        if kind == lab_rules.PIT:
            assert "pit" in res.events and lab.pos[1] == lab_rules.START
        if kind == lab_rules.REST:
            assert "rest" in res.events and lab.rest_used
        if kind == lab_rules.ECHO:
            assert res.echo
    # Привал срабатывает один раз.
    rest = cells[lab_rules.REST]
    lab.pos[1] = next(n for n in lab_rules.neighbors(rest).values() if lab.maze.connected(n, rest, True))
    assert "rest" not in lab.move(1, rest, 1.0).events


def test_hunter_catches_and_releases_to_start() -> None:
    lab = lab_rules.Labyrinth([1], random.Random(9))
    target = _path(lab, lab_rules.START, lab_rules.GATE)[0]
    lab.pos[1] = target
    lab.hunter = next(n for n in lab_rules.neighbors(target).values()
                      if lab.maze.connected(n, target, False) and n != lab_rules.START)
    lab.hunter_next = 0.0
    res = lab.hunter_tick(0.0)
    assert res.moved and res.caught == [1] and lab.is_frozen(1, 1.0)
    assert lab.move(1, lab_rules.START, 1.0).reason == "frozen"
    assert lab.release(tc.CAUGHT_SECONDS + 0.1) == [1] and lab.pos[1] == lab_rules.START
    # На старте Безымянный никого не ловит.
    lab.hunter_next = 0.0
    assert not lab.hunter_tick(100.0).moved


# --- Клавиатуры под лимиты VK ------------------------------------------------------


def _rows(raw: str):
    return json.loads(raw)["buttons"]


def test_map_keyboard_fits_vk() -> None:
    from bot.handlers import raid_trail as handler

    lab = lab_rules.Labyrinth([1, 2, 3], random.Random(1))
    run = handler.TrailRun(battle_id=-1, peers={1: 11, 2: 12, 3: 13}, names={1: "a", 2: "b", 3: "c"},
                           numbers={1: 1, 2: 2, 3: 3}, lab=lab)
    rows = _rows(handler.map_keyboard(run, 1))
    assert len(rows) == lab_rules.N + 1 and all(len(r) <= 5 for r in rows)
    me = [b for r in rows for b in r if b["action"]["label"] == "📍"]
    assert len(me) == 1 and me[0]["color"] == "positive"


def test_arena_keyboard_fits_vk() -> None:
    from bot.handlers import raid_combat
    from bot.keyboards import raid as raid_kb

    stage = trail.NamelessStage(0)
    stage.pos = {1: 0, 2: 4}
    stage.marks = {4}
    battle = SimpleNamespace(participants={1: None, 2: None})
    grid = raid_combat._arena_grid(battle, stage, 1)
    raw = raid_kb.raid_combat_keyboard("mage", {}, subclass_id="elementalist", grid=grid)
    rows = _rows(raw)
    assert len(rows) <= 10 and all(len(r) <= 5 for r in rows)
    assert rows[1][1]["color"] == "negative"  # союзник на отпечатке - красным


# --- Бой с Безымянным ---------------------------------------------------------------


def _arena(n: int = 2):
    players = [combatant(i, 0, name=f"Игрок{i}", level=60) for i in range(1, n + 1)]
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for p in players:
        state.add(p)
    stage = trail.NamelessStage(20_900_000)
    stage.setup(state)
    return stage, state, players


def _step(cid: int, cell: int) -> TickResult:
    return TickResult(actions={cid: DeclaredAction(type=ActionType.SKIP, payload={"step": cell})})


def test_marks_hit_those_who_stayed() -> None:
    stage, state, (a, b) = _arena()
    stage.marks = {stage.pos[a.id], stage.pos[b.id]}
    safe = next(c for c in range(trail.CELLS) if trail.adjacent(stage.pos[a.id], c) and c not in stage.marks)
    stage.after_tick(state, _step(a.id, safe), random.Random(1))
    assert a.current_hp == a.max_hp
    assert b.current_hp == b.max_hp - round(b.max_hp * tc.MARK_PCT)


def test_standing_still_burns() -> None:
    stage, state, (a, b) = _arena()
    rng = random.Random(2)
    for _ in range(tc.BURN_AFTER):
        stage.marks = set()
        stage.ticks = 100  # без новых отпечатков и безымянности
        stage.after_tick(state, TickResult(), rng)
    assert a.current_hp < a.max_hp


def test_nameless_sees_nothing_until_called() -> None:
    stage, state, (a, b) = _arena()
    stage.nameless = {a.id}
    stage.marks = {0, 1}
    assert stage.danger(a.id) == set() and stage.danger(b.id) == {0, 1}
    stage.pos[b.id] = next(c for c in range(trail.CELLS) if trail.adjacent(c, stage.pos[a.id]))
    stage.marks = set()
    stage.after_tick(state, _step(b.id, stage.pos[a.id]), random.Random(3))
    assert a.id not in stage.nameless


def test_marks_always_cover_someone_and_shrink_in_final() -> None:
    stage, state, (a, b) = _arena()
    boss = state.combatants[stage.boss_id]
    stage.ticks = tc.MARK_EVERY - 1
    stage.after_tick(state, TickResult(), random.Random(4))
    assert stage.marks & set(stage.pos.values())
    boss.current_hp = round(boss.max_hp * tc.FINAL_HP) - 1
    stage.marks = set()
    stage.ticks = tc.SHRINK_EVERY - 1
    stage.after_tick(state, TickResult(), random.Random(4))
    assert stage.final and stage.burning


def test_mechanics_damage_goes_through_shields() -> None:
    stage, state, (a, b) = _arena()
    a.apply_effect(EffectKind.SHIELD_POOL, 10**6, 3, a.id)
    stage.marks = {stage.pos[a.id]}
    stage.after_tick(state, TickResult(), random.Random(5))
    assert a.current_hp == a.max_hp


# --- Обработчик: прогон с подменённым VK ---------------------------------------------


class _FakeApi:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str, str | None]] = []
        self.messages = self

    async def send(self, peer_id, message, random_id=0, keyboard=None, attachment=None):
        self.sent.append((peer_id, message, keyboard))
        return 1


class _Msg:
    def __init__(self, peer_id: int, payload: dict) -> None:
        self.peer_id = peer_id
        self._payload = payload

    def get_payload_json(self):
        return self._payload


async def test_handler_walks_the_labyrinth_and_starts_the_fight(monkeypatch) -> None:
    from bot.handlers import raid_combat
    from bot.handlers import raid_trail as handler

    api = _FakeApi()
    monkeypatch.setattr(raid_combat, "_bot_api", api)
    started = []

    async def award(battle_id):
        return {}

    async def begin(battle_id, stage=3, lame=None):
        started.append(stage)

    monkeypatch.setattr(raid_combat, "award_stage", award)
    monkeypatch.setattr(raid_combat, "begin_combat_stage", begin)
    monkeypatch.setattr(handler.tc, "STEP_SECONDS", 0.0)
    monkeypatch.setattr(handler, "_rng", random.Random(4))

    battle = SimpleNamespace(participants={7: SimpleNamespace(peer_id=70, name="Соло")})
    await handler.start(-500, battle)
    run = handler._runs[-500]
    if run.task is not None:
        run.task.cancel()
    lab = run.lab
    _calm(lab)
    assert api.sent and api.sent[-1][2]  # карта пришла клавиатурой

    # Стена - отказ без шага.
    here = lab.pos[7]
    wall = next((n for d, n in lab_rules.neighbors(here).items() if d not in lab.exits(here)), None)
    if wall is not None:
        await handler.on_step(_Msg(70, {"type": "trl", "t": run.token, "c": wall}))
        assert lab.pos[7] == here and api.sent[-1][1] in (handler.tt.REFUSE_WALL, handler.tt.REFUSE_GRATE)

    lab.grate_open = True
    goals = lab.footprints_left() + [lab_rules.GATE]
    for goal in goals:
        for cell in _path(lab, lab.pos[7], goal):
            await handler.on_step(_Msg(70, {"type": "trl", "t": run.token, "c": cell}))
    assert started == [3]
    assert -500 not in handler._runs


async def test_step_takes_time_and_blocks_new_presses(monkeypatch) -> None:
    import asyncio

    from bot.handlers import raid_combat
    from bot.handlers import raid_trail as handler

    api = _FakeApi()
    monkeypatch.setattr(raid_combat, "_bot_api", api)
    monkeypatch.setattr(handler.tc, "STEP_SECONDS", 0.05)
    monkeypatch.setattr(handler, "_rng", random.Random(4))
    battle = SimpleNamespace(participants={7: SimpleNamespace(peer_id=70, name="Соло")})
    await handler.start(-501, battle)
    run = handler._runs[-501]
    run.task.cancel()
    lab = run.lab
    _calm(lab)
    here = lab.pos[7]
    target = lab_rules.neighbors(here)[lab.exits(here)[0]]

    await handler.on_step(_Msg(70, {"type": "trl", "t": run.token, "c": target}))
    assert lab.pos[7] == here and api.sent[-1][1].startswith("🚶")
    await handler.on_step(_Msg(70, {"type": "trl", "t": run.token, "c": target}))
    assert api.sent[-1][1] == handler.tt.REFUSE_WALKING

    await run.walking[7]
    assert lab.pos[7] != here and not run.walking
    handler.abort(-501)
    await asyncio.sleep(0)
