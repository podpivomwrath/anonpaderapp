"""Рейд «Жернова Паломников»: шествие, обоз, Мельник и сквозной заход."""

import json
import random
from types import SimpleNamespace

import pytest

from bot import raid_mill_texts as mt
from bot import raid_texts as rt
from bot.keyboards import raid as raid_kb
from game import raid_procession as rp
from game.combat import raid_mill
from game.combat.raid_field import StageTick
from game.combat.resolver import TickResult, resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.content_loader import load_craft_recipes, load_unique_items
from game.economy import raid_mill_config as mc
from tests.conftest import NoCritRng, combatant

# --- Шествие ----------------------------------------------------------------------


def test_every_beat_is_seen_by_someone_and_everyone_sees_something() -> None:
    for players in range(1, 6):
        for seed in range(10):
            views = rp.deal_views(random.Random(seed), list(range(players)))
            assert all(views[cid] for cid in range(players))
            assert set().union(*views.values()) == set(range(mc.BAR_BEATS))
            if players > 1:
                assert all(len(v) < mc.BAR_BEATS for v in views.values())


def test_rhythm_line_hides_unseen_beats_and_marks_current() -> None:
    proc = rp.Procession(players=[1, 2], rng=random.Random(1))
    line = proc.rhythm_line(1)
    assert line.count("?") == mc.BAR_BEATS - len(proc.views[1])
    assert line.split(" · ")[0].startswith("[")


def _play(proc: rp.Procession, wrong: set[int] = frozenset()) -> rp.BeatResult:
    expected = proc.pattern[proc.position]
    other = next(m for m in rp.MOVES if m != expected)
    for cid in proc.players:
        assert proc.press(cid, other if cid in wrong else expected)
    assert proc.ready
    return proc.resolve()


def test_right_steps_reach_the_goal() -> None:
    proc = rp.Procession(players=[1, 2, 3], rng=random.Random(2))
    for _ in range(mc.STEPS_REQUIRED):
        assert _play(proc).stepped
    assert proc.done


def test_mistake_costs_the_step_and_three_mistakes_roll_the_column_back() -> None:
    proc = rp.Procession(players=[1, 2], rng=random.Random(3))
    for _ in range(4):
        _play(proc)
    result = _play(proc, wrong={2})
    assert not result.stepped and result.wrong == [2] and proc.lame[2] == 1
    _play(proc, wrong={2})
    result = _play(proc, wrong={2})
    assert result.fallen == [2]
    assert proc.lame[2] == 0
    assert proc.steps == 4 - mc.LAG_STEPS_LOST


def test_press_once_per_beat() -> None:
    proc = rp.Procession(players=[1], rng=random.Random(4))
    assert proc.press(1, rp.LEFT)
    assert not proc.press(1, rp.RIGHT)
    assert not proc.press(9, rp.LEFT)


def test_pattern_changes_every_few_beats() -> None:
    proc = rp.Procession(players=[1], rng=random.Random(5))
    changed = [_play(proc).new_pattern for _ in range(mc.PATTERN_EVERY)]
    assert changed[-1] and not any(changed[:-1])


# --- Обоз -------------------------------------------------------------------------


def _session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for c in combatants:
        state.add(c)
    return state


def _cargo(players):
    stage = raid_mill.CargoStage(
        start_id=1000, participants=len(players), order=raid_mill.carry_order([p.subclass_id for p in players]),
    )
    state = _session(*players)
    stage.setup(state)
    return stage, state


def _carry_result(cid: int | None) -> TickResult:
    result = TickResult()
    if cid is not None:
        result.actions[cid] = DeclaredAction(type=ActionType.SKIP, payload={"carry": True})
    return result


def test_carry_rotates_through_subclasses_and_skips_the_dead() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    b = combatant(2, side=0, level=60, subclass_id="poisoner")
    c = combatant(3, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a, b, c])
    assert stage.order == ["guardian", "poisoner"]
    assert stage.can_carry(state, 1) and stage.can_carry(state, 3) and not stage.can_carry(state, 2)
    stage.after_tick(state, _carry_result(1), random.Random(1))
    assert stage.carrier(state) == "poisoner" and stage.progress == 1
    b.current_hp = 0
    assert stage.carrier(state) == "guardian"


def test_only_one_carry_per_turn() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    b = combatant(2, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a, b])
    assert stage.can_carry(state, 1)
    stage.claim()
    assert not stage.can_carry(state, 2)


def test_idle_cargo_drops_a_sack_and_weighs_the_group_down() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a])
    for _ in range(mc.DROP_AFTER):
        out = stage.after_tick(state, _carry_result(None), random.Random(1))
    assert stage.sacks == mc.SACKS_START - 1
    assert a.has_effect(EffectKind.WEAKEN)
    assert any("Груз падает" in line for line in out.lines)


def test_last_sack_lost_kills_the_group() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a])
    stage.sacks = 1
    out = StageTick()
    for _ in range(mc.DROP_AFTER):
        out = stage.after_tick(state, _carry_result(None), random.Random(1))
    assert not a.alive and out.deaths == [1]


def test_cargo_delivered_clears_the_stage_even_with_pilgrims_alive() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a])
    out = StageTick()
    for _ in range(mc.CARGO_STEPS):
        out = stage.after_tick(state, _carry_result(1), random.Random(1))
    assert out.cleared


def test_millstones_cannot_be_killed_so_the_stage_never_ends_by_slaughter() -> None:
    a = combatant(1, side=0, level=60, subclass_id="guardian")
    stage, state = _cargo([a])
    for cid in stage.pilgrim_ids:
        state.combatants[cid].current_hp = 0
    stones = state.combatants[stage.millstones_id]
    result = resolve_tick(state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=stones.id)}, NoCritRng())
    assert stones.alive and not result.finished


# --- Мельник ----------------------------------------------------------------------


def _miller(n: int = 2):
    players = [combatant(i, side=0, level=60, subclass_id="guardian") for i in range(1, n + 1)]
    stage = raid_mill.MillerStage(start_id=2000)
    state = _session(*players)
    stage.setup(state)
    return stage, state, players


def test_hold_spares_the_still_and_crushes_the_restless() -> None:
    stage, state, (a, b) = _miller()
    stage.hold_id = a.id
    result = TickResult()
    result.actions[a.id] = DeclaredAction(type=ActionType.DEFEND)
    out = StageTick()
    stage._check_hold(state, result, out)
    assert a.current_hp == a.max_hp
    stage.hold_id = b.id
    result.actions[b.id] = DeclaredAction(type=ActionType.ATTACK)
    stage._check_hold(state, result, out)
    assert b.current_hp == b.max_hp - round(b.max_hp * mc.FREEZE_CRUSH_PCT)
    assert b.id in out.frozen


def _grind_once(stage, state, who, action=None) -> int:
    """Один помол по who; вернёт снятое здоровье."""
    who.current_hp = who.max_hp
    stage.window_damage = {who.id: 500}
    actions = {who.id: DeclaredAction(type=action)} if action else {}
    stage._grind(state, TickResult(actions=actions), StageTick())
    return who.max_hp - who.current_hp


def test_grind_stacks_are_capped() -> None:
    """2026-10-20: стаков не больше GRIND_MAX_STACKS - дальше не растёт."""
    stage, state, (a, b) = _miller()
    a.max_hp = a.current_hp = 10_000
    hits = [_grind_once(stage, state, a) for _ in range(5)]
    assert hits[1] > hits[0] and hits[2] > hits[1]
    assert hits[2] == hits[3] == hits[4]
    assert hits[4] == round(10_000 * mc.GRIND_BASE_PCT * (1 + mc.GRIND_GROWTH * mc.GRIND_MAX_STACKS))


def test_grind_on_someone_else_resets_stacks() -> None:
    stage, state, (a, b) = _miller()
    a.max_hp = a.current_hp = b.max_hp = b.current_hp = 10_000
    first = _grind_once(stage, state, a)
    _grind_once(stage, state, a)
    _grind_once(stage, state, b)
    assert _grind_once(stage, state, a) == first


def test_defend_halves_the_grind_and_stops_the_stack() -> None:
    stage, state, (a, b) = _miller()
    a.max_hp = a.current_hp = 10_000
    plain = _grind_once(stage, state, a, ActionType.DEFEND)
    assert plain == round(10_000 * mc.GRIND_BASE_PCT * mc.GRIND_DEFEND_MULT)
    assert _grind_once(stage, state, a, ActionType.DEFEND) == plain  # стак не вырос


def test_millstones_respect_shields() -> None:
    stage, state, (a, b) = _miller()
    a.max_hp = a.current_hp = 10_000
    a.apply_effect(EffectKind.SHIELD_POOL, 1_000, 3, a.id)
    stage.window_damage = {a.id: 500}
    stage._grind(state, TickResult(), StageTick())
    assert a.current_hp == 10_000 - (round(10_000 * mc.GRIND_BASE_PCT) - 1_000)


def _hit_on(target_id: int, amount: int):
    return SimpleNamespace(target_id=target_id, amount=amount, missed=False)


def test_chain_ties_one_player_to_the_miller_and_snaps() -> None:
    """2026-10-20: цепь - игрок и Мельник. Не разбили - стягивается и ранит
    только прикованного."""
    stage, state, (a, b) = _miller()
    stage._spawn_chain(state, random.Random(1), StageTick())
    chain = state.combatants[stage.chain_id]
    assert chain.side == 1 and chain.alive
    victim = state.combatants[stage.chained_id]
    other = b if victim is a else a
    for _ in range(mc.CHAIN_TURNS):
        stage._tick_chain(state, TickResult(), StageTick())
    assert stage.chain_id is None and not chain.alive
    assert victim.current_hp < victim.max_hp and other.current_hp == other.max_hp


def test_chain_moves_half_of_the_millers_damage_to_the_player() -> None:
    stage, state, _ = _miller()
    stage._spawn_chain(state, random.Random(1), StageTick())
    boss = state.combatants[stage.boss_id]
    victim = state.combatants[stage.chained_id]
    boss.current_hp -= 1000  # удары игроков этого хода
    result = TickResult(hit_renders=[_hit_on(boss.id, 1000)])
    stage._tick_chain(state, result, StageTick())
    assert boss.current_hp == boss.max_hp - 500
    assert victim.current_hp == victim.max_hp - 500


def test_chain_gives_half_of_heals_and_shields_to_the_miller() -> None:
    from game.combat.resolver import RenderedHeal

    stage, state, _ = _miller()
    stage._spawn_chain(state, random.Random(1), StageTick())
    boss = state.combatants[stage.boss_id]
    victim = state.combatants[stage.chained_id]
    boss.current_hp -= 2000
    victim.current_hp = victim.max_hp - 100  # лечение уже легло: +400
    victim.apply_effect(EffectKind.SHIELD_POOL, 600, 3, victim.id)
    heal = RenderedHeal(source_id=victim.id, target_id=victim.id, source_side=0, target_side=0, label="x",
                        amount=400, hp_before=victim.max_hp - 500, hp_after=victim.max_hp - 100,
                        max_hp=victim.max_hp)
    stage._tick_chain(state, TickResult(heal_renders=[heal]), StageTick())
    assert victim.current_hp == victim.max_hp - 300
    shield = victim.effects_of(EffectKind.SHIELD_POOL)[0]
    assert shield.value == 300
    assert boss.current_hp == boss.max_hp - 2000 + 200 + 300
    # Старый щит на следующем ходу второй раз не делится.
    stage._tick_chain(state, TickResult(), StageTick())
    assert shield.value == 300


def test_broken_chain_does_no_harm() -> None:
    stage, state, (a, b) = _miller()
    stage._spawn_chain(state, random.Random(1), StageTick())
    state.combatants[stage.chain_id].current_hp = 0
    stage._tick_chain(state, TickResult(), StageTick())
    assert stage.chain_id is None and a.current_hp == a.max_hp and b.current_hp == b.max_hp


def test_excommunication_puts_one_subclass_on_cooldown_for_a_turn() -> None:
    stage, state, (a, b) = _miller()
    stage._excommunicate(state, random.Random(1), StageTick())
    assert a.cooldowns and all(v == 1 for v in a.cooldowns.values())


def test_bread_heals_one_and_draws_a_stronger_strike() -> None:
    stage, state, (a, b) = _miller()
    a.current_hp = a.max_hp // 2
    stage.bread_open = True
    assert stage.take_bread(state, a.id)
    assert a.current_hp > a.max_hp // 2
    assert stage.take_bread(state, b.id) is None
    boss = state.combatants[stage.boss_id]
    hits = boss.scripted_hit(boss, state, NoCritRng())
    assert hits[0].target_id == a.id
    normal = raid_mill.MillerAI(raid_mill.MillerStage(0))
    plain = normal(boss, state, NoCritRng())[0]
    assert hits[0].amount > plain.amount


def test_final_phase_shortens_the_turn() -> None:
    stage, state, _ = _miller()
    boss = state.combatants[stage.boss_id]
    boss.current_hp = round(boss.max_hp * mc.FINAL_HP) - 1
    stage.after_tick(state, TickResult(), random.Random(1))
    assert state.turn_seconds == mc.FINAL_TURN_SECONDS


# --- Подключение ------------------------------------------------------------------


def test_raid_is_listed_and_rewards_greaves() -> None:
    assert rt.RAID_TITLES[mc.RAID_MILL_ID] == mt.BTN_MILL
    assert load_unique_items()[mc.RAID_UNIQUE_ITEM_ID].slot == "legs"
    assert mc.RAID_UNIQUE_ITEM_ID in load_craft_recipes()


def test_raid_keyboard_with_stage_button_fits_vk() -> None:
    kb = json.loads(raid_kb.raid_combat_keyboard("warrior", {}, "blood_knight", extra=[(mt.BTN_CARRY, {"type": "raid_carry"})]))
    rows = kb["buttons"]
    assert rows[0][0]["action"]["label"] == mt.BTN_CARRY
    assert len(rows) <= 10 and all(len(r) <= 2 for r in rows)


# --- Сквозной заход: шествие -> обоз -> Мельник ----------------------------------


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


def _member(cid: int, subclass: str, base: str):
    character = SimpleNamespace(id=cid, name=f"Игрок{cid}", base_class=base, subclass=subclass, level=60)
    stats = SimpleNamespace(strength=60, agility=60, intellect=60, vitality=2000, will=60)
    return SimpleNamespace(character=character, stats=stats, gear_bonus={}, buff_modifiers={}, peer_id=100 + cid)


async def test_full_run_reaches_the_miller(monkeypatch) -> None:
    from bot.handlers import raid_combat, raid_procession
    from game.combat.tick_engine import InMemoryActionStore, TickEngine
    from game.economy import raid_config as rc

    monkeypatch.setattr(rc, "STAGE_TRANSITION_PAUSE_MIN_SECONDS", 0)
    monkeypatch.setattr(rc, "STAGE_TRANSITION_PAUSE_MAX_SECONDS", 0)
    api = _Api()
    engine = TickEngine(
        InMemoryActionStore(),
        on_tick_resolved=raid_combat.on_raid_tick_resolved,
        on_battle_finished=raid_combat.on_raid_battle_finished,
    )
    engine.start()
    raid_combat.setup(engine, api)
    members = [_member(1, "guardian", "warrior"), _member(2, "poisoner", "rogue")]
    try:
        await raid_combat.start_raid(None, members, random.Random(7), raid_id=mc.RAID_MILL_ID, run_id=-777)
        battle_id = raid_combat._peer_battle[101]
        battle = raid_combat._battles[battle_id]

        # Этап 1: все шагают в такт.
        run = raid_procession._runs[battle_id]
        while battle_id in raid_procession._runs:
            proc = run.procession
            move = proc.pattern[proc.position]
            for m in members:
                await raid_procession.on_step(_Msg(m.peer_id, {"type": "mpr", "t": run.token, "b": proc.beat, "m": move}))
        assert battle.stage == 2
        cargo = battle.field_stage
        assert isinstance(cargo, raid_mill.CargoStage)
        assert battle.pending_rewards and battle.pending_rewards[0].stage == 1

        # Этап 2: не тот подкласс хватает груз - ход впустую.
        state = engine.sessions[battle_id]
        wrong = next(m for m in members if m.character.subclass != cargo.carrier(state))
        right = next(m for m in members if m.character.subclass == cargo.carrier(state))
        await raid_combat.raid_carry(_Msg(wrong.peer_id, {"type": "raid_carry"}))
        await raid_combat.raid_carry(_Msg(right.peer_id, {"type": "raid_carry"}))
        assert cargo.progress == 1
        while battle.stage == 2:
            state = engine.sessions[battle_id]
            carrier = cargo.carrier(state)
            for m in members:
                if not state.combatants[m.character.id].alive:
                    continue
                if m.character.subclass == carrier and not cargo.carried:
                    await raid_combat.raid_carry(_Msg(m.peer_id, {"type": "raid_carry"}))
                else:
                    await raid_combat.raid_defend(_Msg(m.peer_id, {"type": "raid_defend"}))
            if battle_id not in raid_combat._battles:
                pytest.fail("группа погибла на обозе")
        assert battle.stage == 3
        assert isinstance(battle.field_stage, raid_mill.MillerStage)
        boards = [s for s in api.sent if "Груз" in (s.get("message") or "")]
        assert boards
    finally:
        raid_combat.abort_run(-777)
        engine.shutdown()
