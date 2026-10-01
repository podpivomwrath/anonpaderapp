"""Рейд «Безмогильное поле»: механики трёх этапов (game/combat/raid_field.py)
и два расширения резолвера, на которых они держатся (hp_floor,
incoming_hit_hook)."""

import random

from game.combat import raid_field as rf
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.economy import craft_config as cc
from game.economy import crafting
from game.economy import raid_field_config as fc
from services import naming
from tests.conftest import NoCritRng, combatant


def _session(players: int = 3) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for i in range(1, players + 1):
        state.add(combatant(i, side=0, level=60, vitality=400, strength=150))
    return state


def _attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def _skip() -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKIP)


def _tick(state, actions, rng=None):
    state.tick_number += 1
    return resolve_tick(state, actions, rng or NoCritRng())


# --- Резолвер: пол HP и фильтр удара ------------------------------------------


def test_hp_floor_keeps_the_creature_alive_and_out_of_deaths() -> None:
    state = _session(1)
    boss = combatant(9, side=1, kind="mob", level=60)
    boss.max_hp = boss.current_hp = 5
    boss.hp_floor = 1
    state.add(boss)
    result = _tick(state, {1: _attack(9)})
    assert boss.current_hp == 1
    assert 9 not in result.deaths
    assert not result.finished


def test_incoming_hook_rewrites_damage_before_it_lands() -> None:
    state = _session(1)
    boss = combatant(9, side=1, kind="mob", level=60, vitality=500)
    boss.incoming_hit_hook = lambda hit, source, amount: 0
    state.add(boss)
    before = boss.current_hp
    result = _tick(state, {1: _attack(9)})
    assert boss.current_hp == before
    assert any(h.target_id == 9 and h.amount == 0 for h in result.hit_renders)


# --- Этап 1: туман ------------------------------------------------------------


def test_fog_clears_when_the_last_bearer_falls_and_skeletons_go_down() -> None:
    state = _session(2)
    stage = rf.FogStage(100)
    stage.setup(state)
    assert stage.reward_ids == set(stage.bearer_ids)
    for cid in stage.bearer_ids[:-1]:
        state.combatants[cid].current_hp = 0
    last = state.combatants[stage.bearer_ids[-1]]
    last.current_hp = 1
    result = _tick(state, {1: _attack(last.id), 2: _attack(last.id)})
    out = stage.after_tick(state, result)
    assert out.cleared
    assert all(not state.combatants[cid].alive for cid in stage.skeleton_ids)


def test_fog_raises_skeletons_on_schedule_up_to_the_cap() -> None:
    state = _session(2)
    stage = rf.FogStage(100)
    stage.setup(state)
    for _ in range(fc.SKELETON_RAISE_EVERY * 6):
        stage.after_tick(state, _tick(state, {1: _skip(), 2: _skip()}))
        alive = sum(1 for cid in stage.skeleton_ids if state.combatants[cid].alive)
        assert alive <= fc.SKELETON_ALIVE_CAP
    assert len(stage.skeleton_ids) > fc.SKELETONS_AT_START


def test_skeletons_never_pay_loot() -> None:
    state = _session(1)
    stage = rf.FogStage(100)
    stage.setup(state)
    assert not (set(stage.skeleton_ids) & stage.reward_ids)


# --- Этап 2: Тот, кто зовёт ---------------------------------------------------


def _summoner_stage(players: int = 3):
    state = _session(players)
    stage = rf.SummonerStage(200, players)
    stage.setup(state)
    return state, stage


def _cast(stage, state, kind, rng=None):
    """Навык нужного вида - перебираем ходы, пока призыватель не выберет его."""
    rng = rng or random.Random(3)
    for _ in range(200):
        out = rf.StageTick()
        stage._cast(state, rng, out)
        obj = stage.objects[-1] if stage.objects else None
        if obj is not None and obj.kind == kind:
            return obj
        for o in stage.objects:
            state.combatants[o.combatant_id].current_hp = 0
        stage.objects.clear()
        stage.last_cast = None
    raise AssertionError(f"навык {kind} не выпал")


def test_summoner_does_not_die_he_takes_up_the_halberd() -> None:
    state, stage = _summoner_stage()
    summoner = state.combatants[stage.summoner_id]
    summoner.current_hp = 2
    result = _tick(state, {1: _attack(summoner.id), 2: _attack(summoner.id), 3: _attack(summoner.id)})
    out = stage.after_tick(state, result, random.Random(1))
    assert summoner.alive
    assert out.cleared


def test_objects_left_at_the_halberd_make_the_general_stronger() -> None:
    state, stage = _summoner_stage()
    _cast(stage, state, rf.BELL)
    summoner = state.combatants[stage.summoner_id]
    summoner.current_hp = 1
    out = stage.after_tick(state, _tick(state, {1: _skip(), 2: _skip(), 3: _skip()}), random.Random(1))
    assert out.cleared and stage.leftover == 1

    general_state = _session(3)
    general_stage = rf.GeneralStage(300, leftover_objects=stage.leftover)
    general_stage.setup(general_state)
    general = general_state.combatants[general_stage.general_id]
    assert general.effect_total(EffectKind.DAMAGE_BUFF) == fc.OBJECT_LEFTOVER_DAMAGE_BONUS


def test_hands_hold_the_victim_and_drag_them_under_if_nobody_breaks_them() -> None:
    state, stage = _summoner_stage()
    hands = _cast(stage, state, rf.HANDS)
    victim = state.combatants[hands.victim_id]
    assert victim.has_effect(EffectKind.FREEZE)
    for _ in range(fc.HANDS_TURNS):
        out = stage.after_tick(state, _tick(state, {}), random.Random(1))
    assert not victim.alive
    assert victim.id in out.deaths


def test_breaking_the_hands_frees_the_victim() -> None:
    state, stage = _summoner_stage()
    hands = _cast(stage, state, rf.HANDS)
    victim = state.combatants[hands.victim_id]
    state.combatants[hands.combatant_id].current_hp = 1
    rescuers = [c for c in (1, 2, 3) if c != victim.id]
    result = _tick(state, {cid: _attack(hands.combatant_id) for cid in rescuers})
    out = stage.after_tick(state, result, random.Random(1))
    assert victim.alive
    assert not victim.has_effect(EffectKind.FREEZE)
    assert victim.id not in out.frozen


def test_hands_victim_is_reported_frozen_for_the_auto_skip() -> None:
    state, stage = _summoner_stage()
    hands = _cast(stage, state, rf.HANDS)
    out = stage.after_tick(state, _tick(state, {}), random.Random(1))
    assert hands.victim_id in out.frozen


def test_nobody_is_grabbed_or_chained_in_a_solo_run() -> None:
    state, stage = _summoner_stage(players=1)
    rng = random.Random(5)
    for _ in range(60):
        stage._cast(state, rng, rf.StageTick())
        for o in stage.objects:
            state.combatants[o.combatant_id].current_hp = 0
    assert stage.objects
    assert {o.kind for o in stage.objects}.isdisjoint({rf.HANDS, rf.CHAIN})


def test_mound_shields_the_summoner_until_different_players_strike_it() -> None:
    state, stage = _summoner_stage(players=3)
    mound_obj = _cast(stage, state, rf.MOUND)
    mound = state.combatants[mound_obj.combatant_id]
    summoner = state.combatants[stage.summoner_id]
    before = summoner.current_hp

    # Двое бьют призывателя, один - курган: урон по призывателю гаснет.
    result = _tick(state, {1: _attack(summoner.id), 2: _attack(summoner.id), 3: _attack(mound.id)})
    stage.after_tick(state, result, random.Random(1))
    assert summoner.current_hp == before
    assert mound.alive

    # Тот же боец второй раз - курган не трескается.
    hp = mound.current_hp
    result = _tick(state, {3: _attack(mound.id)})
    stage.after_tick(state, result, random.Random(1))
    assert mound.current_hp == hp

    # Двое других - курган рушится.
    result = _tick(state, {1: _attack(mound.id), 2: _attack(mound.id)})
    stage.after_tick(state, result, random.Random(1))
    assert not mound.alive


def test_bell_heals_the_summoner_while_it_rings() -> None:
    state, stage = _summoner_stage()
    _cast(stage, state, rf.BELL)
    summoner = state.combatants[stage.summoner_id]
    summoner.current_hp = summoner.max_hp // 2
    before = summoner.current_hp
    stage.after_tick(state, _tick(state, {}), random.Random(1))
    assert summoner.current_hp > before


def test_chain_passes_enemy_damage_to_the_other_end() -> None:
    state, stage = _summoner_stage()
    chain = _cast(stage, state, rf.CHAIN)
    a, b = state.combatants[chain.victim_id], state.combatants[chain.partner_id]
    a_before, b_before = a.current_hp, b.current_hp
    stage.ai.turn = fc.SUMMONER_CURSE_EVERY - 1  # следующий ход - проклятие по всем
    result = _tick(state, {})
    hit_a = sum(h.amount for h in result.hit_renders if h.target_id == a.id and h.source_side == 1)
    hit_b = sum(h.amount for h in result.hit_renders if h.target_id == b.id and h.source_side == 1)
    assert hit_a > 0 and hit_b > 0
    stage.after_tick(state, result, random.Random(1))
    # каждый конец получил свой удар и копию удара по другому
    assert a_before - a.current_hp == hit_a + hit_b
    assert b_before - b.current_hp == hit_a + hit_b


def test_open_grave_strikes_its_victim_through_the_normal_hit() -> None:
    state, stage = _summoner_stage()
    grave = _cast(stage, state, rf.GRAVE)
    victim_id = grave.victim_id
    for _ in range(fc.GRAVE_TURNS):
        out = stage.after_tick(state, _tick(state, {}), random.Random(1))
    assert stage.ai.grave_strike_on == victim_id
    assert any("Могила открывается" in line for line in out.lines)
    result = _tick(state, {})
    assert any(h.label == "Чужая могила" and h.target_id == victim_id for h in result.hit_renders)


def test_broken_grave_never_strikes() -> None:
    state, stage = _summoner_stage()
    grave = _cast(stage, state, rf.GRAVE)
    state.combatants[grave.combatant_id].current_hp = 0
    for _ in range(fc.GRAVE_TURNS + 1):
        stage.after_tick(state, _tick(state, {}), random.Random(1))
    assert stage.ai.grave_strike_on is None


# --- Этап 3: Генерал ----------------------------------------------------------


def _general(players: int = 5):
    state = _session(players)
    stage = rf.GeneralStage(300)
    stage.setup(state)
    return state, stage, state.combatants[stage.general_id]


def _force(stage, general, state, stance, target_id=1):
    stage.ai.active = stance
    stage.announced = stance
    stage.ai.target_id = target_id
    if stance == rf.CHALLENGE:
        stage.ai.challenge_left = fc.CHALLENGE_TURNS
    if stance == rf.GUARD:
        general.apply_effect(EffectKind.BLOOD_REFLECT, fc.GUARD_REFLECT, 1, general.id)
    if stance == rf.COUNT:
        stage.count_allowed = stage._count_allowed(state)


def test_guard_returns_the_blow_and_does_not_attack() -> None:
    state, stage, general = _general()
    _force(stage, general, state, rf.GUARD)
    result = _tick(state, {1: _attack(general.id)})
    assert any(h.target_id == 1 and h.label == "шипы" for h in result.hit_renders)
    assert not any(h.source_id == general.id and h.label != "шипы" for h in result.hit_renders)


def test_iron_stance_ignores_plain_attacks() -> None:
    state, stage, general = _general()
    _force(stage, general, state, rf.IRON)
    before = general.current_hp
    _tick(state, {1: _attack(general.id), 2: _attack(general.id)})
    assert general.current_hp == before


def test_iron_stance_doubles_skills() -> None:
    _, stage, _ = _general()
    stage.ai.active = rf.IRON
    hit = type("H", (), {"label": "Сокрушающий удар", "is_dot": False})()
    assert stage.ai.hook(hit, None, 100) == round(100 * fc.IRON_SKILL_MULT)


def test_challenge_lets_only_the_called_player_wound_him() -> None:
    state, stage, general = _general()
    _force(stage, general, state, rf.CHALLENGE, target_id=2)
    before = general.current_hp
    _tick(state, {1: _attack(general.id), 3: _attack(general.id)})
    assert general.current_hp == before
    _tick(state, {2: _attack(general.id)})
    assert general.current_hp < before


def test_count_answers_everyone_who_struck_past_the_limit() -> None:
    state, stage, general = _general(players=5)
    _force(stage, general, state, rf.COUNT)
    assert stage.count_allowed == 3
    result = _tick(state, {cid: _attack(general.id) for cid in (1, 2, 3, 4)})
    hp_before = {cid: state.combatants[cid].current_hp for cid in (1, 2, 3, 4, 5)}
    out = stage.after_tick(state, result, random.Random(1), {})
    assert any("Отвечает каждому" in line for line in out.lines)
    for cid in (1, 2, 3, 4):
        assert state.combatants[cid].current_hp < hp_before[cid]
    assert state.combatants[5].current_hp == hp_before[5]


def test_count_within_the_limit_costs_nothing() -> None:
    state, stage, general = _general(players=5)
    _force(stage, general, state, rf.COUNT)
    result = _tick(state, {cid: _attack(general.id) for cid in (1, 2, 3)})
    hp_before = {cid: state.combatants[cid].current_hp for cid in (1, 2, 3)}
    stage.after_tick(state, result, random.Random(1), {})
    assert all(state.combatants[cid].current_hp == hp_before[cid] for cid in (1, 2, 3))


def test_stances_alternate_with_plain_strikes_and_hint_only_once() -> None:
    state, stage, general = _general()
    rng = random.Random(9)
    hints = 0
    for _ in range(40):
        before = stage.ai.active
        out = stage.after_tick(state, _tick(state, {}, rng), rng, {})
        hints += sum(1 for line in out.lines if not line.startswith("⚠️") and line in {
            h.format(allowed=stage.count_allowed) for h in rf._HINT.values()
        })
        if before in rf.STANCES and before != rf.CHALLENGE:
            assert stage.ai.active == rf.STRIKE
        for p in (1, 2, 3, 4, 5):
            state.combatants[p].current_hp = state.combatants[p].max_hp
    assert hints <= len(rf.STANCES)


def test_feint_shows_one_stance_and_does_another() -> None:
    state, stage, general = _general()
    general.current_hp = general.max_hp // 4  # ниже порога обманки, выше знамени

    class AlwaysFeint(random.Random):
        def random(self):
            return 0.0

        def choice(self, seq):
            return rf.GUARD if rf.GUARD in seq else seq[0]

    out = rf.StageTick()
    stage._announce(state, general, AlwaysFeint(), {}, out)
    assert stage.announced == rf.GUARD
    assert stage.ai.active == rf.REAP
    assert "задней ноге" in out.lines[0]


def test_no_count_stance_for_a_tiny_group() -> None:
    state, stage, general = _general(players=2)
    rng = random.Random(1)
    for _ in range(80):
        stage.last_stance = None
        out = rf.StageTick()
        stage._announce(state, general, rng, {}, out)
        assert stage.announced != rf.COUNT


def test_banner_raises_damage_every_turn_under_it() -> None:
    state, stage, general = _general()
    general.current_hp = round(general.max_hp * fc.BANNER_HP_FRACTION) - 1
    rng = random.Random(2)
    stage.after_tick(state, _tick(state, {}, rng), rng, {})
    first = general.effect_total(EffectKind.DAMAGE_BUFF)
    stage.after_tick(state, _tick(state, {}, rng), rng, {})
    assert general.effect_total(EffectKind.DAMAGE_BUFF) > first > 0


# --- Награда: панцирь ---------------------------------------------------------


def test_cuirass_rolls_only_vitality_and_the_class_stat() -> None:
    from services import item_service

    cuirass = item_service.unique_items()["general_cuirass"]
    assert cuirass.slot == "armor"
    for seed in range(30):
        stats = crafting.roll_boss_item_stats(random.Random(seed), cuirass.power, "agi", cuirass.weights)
        assert set(stats) <= {"vit", "agi"}


def test_cuirass_crafts_keep_to_vitality_and_the_class_stat() -> None:
    for spec in cc.SPECS:
        weights = crafting.spec_weights("general_cuirass", spec)
        assert set(weights) == {"vit", "primary"}
        for seed in range(20):
            base, _ = crafting.roll_crafted_stats(
                random.Random(seed), spec, 45, "int", 2, "common", weights=weights,
            )
            assert set(base) <= {"vit", "int"}


def test_scalpel_keeps_the_shared_spec_weights() -> None:
    for spec in cc.SPECS:
        assert crafting.spec_weights("surgeon_scalpel", spec) == cc.SPEC_WEIGHTS[spec]


def test_cuirass_crafts_have_their_own_icon_keys() -> None:
    item = type("I", (), {"craft_spec": "tank", "craft_source_id": "general_cuirass",
                          "slot": "armor", "name": "Нагрудник Знаменосца"})()
    assert naming.item_icon_key(item) == "craft:general_cuirass:tank"
    item.craft_source_id = "surgeon_scalpel"
    assert naming.item_icon_key(item) == "craft:tank"
