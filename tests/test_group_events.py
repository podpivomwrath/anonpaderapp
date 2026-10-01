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
    assert {e.mechanic for e in events} == {"split", "vote", "roles", "rescue"}
    for event in events:
        choices = {
            cid: (ge.choices_of(event, cid, 1)[0][0] if ge.choices_of(event, cid, 1) else None)
            for cid in MEMBERS
        }
        outcome = ge.resolve(event, MEMBERS, choices, random.Random(1), leader_id=1, victim_id=1)
        assert outcome.summary


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
