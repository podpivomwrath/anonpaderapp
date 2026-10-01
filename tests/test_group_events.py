"""Групповые события исследования: подсчёт исходов (game/world/group_events.py)
и целостность контента (content/events/group_scenes.json)."""

import random

from game.world import group_events as ge
from game.world.scene_events import SceneResult

MEMBERS = {1: "Аня", 2: "Борис", 3: "Вера"}


def _event(event_id: str) -> ge.GroupEvent:
    event = ge.event_by_id(event_id)
    assert event is not None
    return event


# --- Контент ------------------------------------------------------------------


def test_every_mechanic_has_an_event_and_all_resolve() -> None:
    events = ge.content().events
    assert {e.mechanic for e in events} == {
        "split", "vote", "roles", "rescue", "volunteer", "circle", "pot", "branches", "nest", "siege",
    }
    for event in events:
        state = ge.initial_state(event, list(MEMBERS))
        for pick in (0, -1):
            choices = {}
            for cid in MEMBERS:
                options = ge.choices_of(event, cid, 1, state, len(MEMBERS))
                choices[cid] = options[pick][0] if options else None
            outcome = ge.resolve(event, MEMBERS, choices, random.Random(1), leader_id=1, victim_id=1, state=state)
            assert outcome.summary, event.id


def test_every_event_has_an_image_prompt() -> None:
    from pathlib import Path

    prompts = (Path(__file__).resolve().parents[1] / "tools" / "event_art_prompts.md").read_text(encoding="utf-8")
    for event in ge.content().events:
        assert f"`{event.id}`" in prompts, event.id


def test_event_ids_are_unique() -> None:
    ids = [e.id for e in ge.content().events]
    assert len(ids) == len(set(ids))


def test_group_reward_is_higher_than_solo() -> None:
    scaled = ge.scale(SceneResult(reward=1.0, xp=1.0, gold=2.0, damage=[10, 20]))
    assert ge.GROUP_REWARD_MULT > 1
    assert scaled.reward == ge.GROUP_REWARD_MULT
    assert scaled.gold == 2.0 * ge.GROUP_REWARD_MULT
    assert scaled.damage == [10, 20]  # урон не растёт


# --- Делёж --------------------------------------------------------------------


def test_split_everyone_shares() -> None:
    event = _event("g_deserters_cache")
    out = ge.resolve(event, MEMBERS, {1: "share", 2: "share", 3: "share"}, random.Random(1))
    assert all(out.results[i] is event.all_share for i in MEMBERS)


def test_split_lone_taker_gets_everything() -> None:
    event = _event("g_deserters_cache")
    out = ge.resolve(event, MEMBERS, {1: "take", 2: "share", 3: "share"}, random.Random(1))
    assert out.results[1] is event.taker
    assert out.results[2] is event.robbed and out.results[3] is event.robbed
    assert any("Аня" in line and "Себе" in line for line in out.summary)


def test_split_two_takers_ruin_it_for_all() -> None:
    event = _event("g_deserters_cache")
    out = ge.resolve(event, MEMBERS, {1: "take", 2: "take", 3: "share"}, random.Random(1))
    assert all(out.results[i] is event.greedy for i in MEMBERS)


def test_split_silent_player_counts_as_sharing() -> None:
    event = _event("g_deserters_cache")
    assert ge.default_choice(event) == "share"


# --- Голосование ----------------------------------------------------------------


def test_vote_majority_wins_and_stays_anonymous() -> None:
    event = _event("g_ravine_fork")
    out = ge.resolve(event, MEMBERS, {1: "2", 2: "2", 3: "0"}, random.Random(1), leader_id=3)
    assert any(event.options[2].label in line for line in out.summary if line.startswith("Группа"))
    assert not any(name in " ".join(out.summary) for name in MEMBERS.values())
    assert len({id(r) for r in out.results.values()}) == 1  # всем один исход


def test_vote_tie_goes_to_the_leader() -> None:
    event = _event("g_ravine_fork")
    members = {1: "Аня", 2: "Борис"}
    out = ge.resolve(event, members, {1: "0", 2: "2"}, random.Random(1), leader_id=2)
    assert any(event.options[2].label in line for line in out.summary if line.startswith("Группа"))
    assert any("лидер" in line for line in out.summary)


def test_vote_ambush_means_combat() -> None:
    event = _event("g_ravine_fork")
    tunnel = next(i for i, o in enumerate(event.options) if any(r.combat for r in o.outcomes))
    seen = set()
    for seed in range(40):
        out = ge.resolve(event, MEMBERS, {i: str(tunnel) for i in MEMBERS}, random.Random(seed))
        seen.add(out.combat)
    assert seen == {True, False}


# --- Роли ---------------------------------------------------------------------


def test_roles_success_when_every_role_is_covered() -> None:
    event = _event("g_rockfall")
    out = ge.resolve(event, MEMBERS, {1: "hold", 2: "hold", 3: "dig"}, random.Random(1))
    assert all(out.results[i] is event.success for i in MEMBERS)
    assert not out.combat


def test_roles_too_few_holders_brings_the_roof_down() -> None:
    event = _event("g_rockfall")
    out = ge.resolve(event, MEMBERS, {1: "hold", 2: "dig", 3: "dig"}, random.Random(1))
    hold = next(r for r in event.roles if r.id == "hold")
    assert all(out.results[i] is hold.shortfall for i in MEMBERS)


def test_roles_nobody_digging_draws_a_patrol() -> None:
    event = _event("g_rockfall")
    out = ge.resolve(event, MEMBERS, {1: "hold", 2: "hold", 3: "hold"}, random.Random(1))
    assert out.combat


# --- Спасение -----------------------------------------------------------------


def test_rescue_enough_pullers_save_the_victim() -> None:
    event = _event("g_bog")
    out = ge.resolve(event, MEMBERS, {2: "pull", 3: "leave"}, random.Random(1), victim_id=1)
    assert out.results[1] is event.saved and out.results[2] is event.saved
    assert out.results[3] is event.left


def test_rescue_everyone_leaves_and_the_victim_is_ruined() -> None:
    event = _event("g_bog")
    out = ge.resolve(event, MEMBERS, {2: "leave", 3: "leave"}, random.Random(1), victim_id=1)
    assert out.results[1] is event.drowned
    assert out.results[1].ruin
    assert out.results[2] is event.left


def test_rescue_victim_has_no_buttons() -> None:
    event = _event("g_bog")
    assert ge.choices_of(event, 1, victim_id=1) == []
    assert ge.choices_of(event, 2, victim_id=1)


def test_no_event_ever_kills() -> None:
    """Худшее - разорение, как в соло: смерть от события не предусмотрена."""
    for event in ge.content().events:
        results = [event.all_share, event.taker, event.robbed, event.greedy, event.success,
                   event.saved, event.left, event.drowned, event.strained]
        results += [r.shortfall for r in event.roles]
        results += [o for opt in event.options for o in opt.outcomes]
        for r in results:
            if r is not None and r.damage:
                assert max(r.damage) < 100


# --- Алтарь -------------------------------------------------------------------


def test_altar_volunteers_split_the_toll_and_everyone_is_blessed() -> None:
    event = _event("g_blood_altar")
    out = ge.resolve(event, MEMBERS, {1: "volunteer", 2: "volunteer", 3: "silent"}, random.Random(1))
    assert out.results[1].damage == [event.toll_pct / 2] * 2
    assert out.results[3] is event.blessing
    assert out.results[1].effect == event.blessing.effect


def test_altar_takes_double_when_nobody_volunteers() -> None:
    event = _event("g_blood_altar")
    out = ge.resolve(event, MEMBERS, {}, random.Random(1))
    assert len(out.results) == 1
    (victim_result,) = out.results.values()
    assert victim_result.damage[0] == min(event.toll_pct * 2, 80)
    assert victim_result.effect is None


# --- Круг ---------------------------------------------------------------------


def test_circle_closes_only_when_every_stone_is_taken_once() -> None:
    event = _event("g_ritual_circle")
    assert len(ge.choices_of(event, 1, None, {}, 3)) == 3  # камней столько, сколько людей
    out = ge.resolve(event, MEMBERS, {1: "0", 2: "1", 3: "2"}, random.Random(1))
    assert all(out.results[i] is event.lit_all for i in MEMBERS)
    out = ge.resolve(event, MEMBERS, {1: "0", 2: "0", 3: "2"}, random.Random(1))
    assert out.results[3] is event.lit_partial
    assert out.results[1] is event.dark and out.results[2] is event.dark


# --- Роли с необязательной ролью и бонусом ------------------------------------


def test_stranger_searchers_get_their_bonus_on_success() -> None:
    event = _event("g_wounded_stranger")
    for seed in range(30):
        out = ge.resolve(event, MEMBERS, {1: "guard", 2: "heal", 3: "search"}, random.Random(seed))
        if not out.combat:
            assert out.results[3].reward > out.results[1].reward
            assert out.results[1].trail == "map"
            return
    raise AssertionError("ни одного мирного исхода")


def test_stranger_without_a_guard_is_an_ambush() -> None:
    event = _event("g_wounded_stranger")
    out = ge.resolve(event, MEMBERS, {1: "heal", 2: "search", 3: "search"}, random.Random(1))
    assert out.combat


# --- Котёл --------------------------------------------------------------------


def test_pot_charges_stakes_pays_double_and_is_not_scaled() -> None:
    event = _event("g_bone_pot")
    wins = losses = 0
    for seed in range(60):
        out = ge.resolve(event, MEMBERS, {1: "l", 2: "s", 3: "0"}, random.Random(seed))
        assert not out.scaled
        assert out.charges == {1: 6.0, 2: 1.0}
        assert 3 not in out.results
        if out.results[1].gold:
            wins += 1
            assert out.results[1].gold == 12.0
        else:
            losses += 1
    assert wins and losses


def test_pot_odds_grow_with_stakers_up_to_the_cap() -> None:
    event = _event("g_bone_pot")
    five = {i: "Игрок" for i in range(1, 6)}
    out = ge.resolve(event, five, {i: "s" for i in five}, random.Random(1))
    assert f"Шанс {round(event.pot_max * 100)}%" in " ".join(out.summary)


# --- Караван ------------------------------------------------------------------


def test_caravan_joint_reward_only_when_both_branches_succeed() -> None:
    event = _event("g_dead_caravan")
    joint_seen = alone = False
    for seed in range(80):
        out = ge.resolve(event, MEMBERS, {1: "wagons", 2: "driver", 3: "driver"}, random.Random(seed))
        rewards = {i: r.reward for i, r in out.results.items()}
        if "Обе ветки сошлись." in out.summary:
            joint_seen = True
            assert rewards[1] > event.branches[0].success.reward
    for seed in range(20):
        out = ge.resolve(event, MEMBERS, {1: "wagons", 2: "wagons", 3: "wagons"}, random.Random(seed))
        alone = alone or "Обе ветки сошлись." not in out.summary
    assert joint_seen and alone


# --- Гнездо -------------------------------------------------------------------


def test_nest_leavers_cash_out_and_climbers_go_on() -> None:
    event = _event("g_scavenger_nest")
    state = ge.initial_state(event, list(MEMBERS))

    class Calm(random.Random):
        def random(self):
            return 0.99

    out = ge.resolve(event, MEMBERS, {1: "climb", 2: "climb", 3: "leave"}, Calm(), state=state)
    assert out.next_round and out.active == [1, 2]
    assert out.results[3].reward == 0.0
    assert out.state["bank"][1] == event.step_reward
    out2 = ge.resolve(event, MEMBERS, {1: "leave", 2: "climb"}, Calm(), state=out.state)
    assert out2.results[1].reward == event.step_reward
    assert out2.active == [2]


def test_nest_alarm_takes_the_climbers_bank() -> None:
    event = _event("g_scavenger_nest")
    state = {"round": 4, "bank": {1: 2.1, 2: 0.0}, "active": [1]}

    class Loud(random.Random):
        def random(self):
            return 0.0

    out = ge.resolve(event, {1: "Аня", 2: "Борис"}, {1: "climb"}, Loud(), state=state)
    assert not out.next_round
    assert out.results[1].ruin and out.results[1].reward == 0


# --- Осада --------------------------------------------------------------------


def test_siege_retreat_pays_what_was_taken() -> None:
    event = _event("g_tower_siege")
    out = ge.resolve(event, MEMBERS, {i: "retreat" for i in MEMBERS}, random.Random(1),
                     state={"stage": 1, "bank": 1.5})
    assert all(out.results[i].reward == 1.5 for i in MEMBERS)
    assert not out.next_round


def test_siege_full_climb_ends_with_the_final_prize() -> None:
    event = _event("g_tower_siege")

    class Lucky(random.Random):
        def random(self):
            return 0.99

    state = ge.initial_state(event, list(MEMBERS))
    for _ in range(len(event.stages)):
        out = ge.resolve(event, MEMBERS, {i: "bypass" for i in MEMBERS}, Lucky(), state=state)
        state = out.state
    assert not out.next_round
    expected = sum(stage.options[1].gain for stage in event.stages) + event.final.reward
    assert abs(out.results[1].reward - expected) < 1e-9
    assert out.results[1].item
