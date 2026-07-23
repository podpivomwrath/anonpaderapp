"""Классовые испытания (патч 12): трекер условий, разблокировка баффов.

_report() даёт "инертные" дефолты (не удовлетворяют условиям большинства
типов), но некоторые дефолты (hp_min_pct=1.0, start_hp_pct=1.0) естественно
удовлетворяют "никогда не опускался ниже X%"-условия того же подкласса —
поэтому проверяем КОНКРЕТНОЕ испытание через _unlocked/_progress, а не
равенство всего списка unlocked (в нём могут оказаться и другие id)."""

from game.combat.battle_report import BattleReport
from services import trial_service


def _report(**kwargs) -> BattleReport:
    base = dict(
        won=True, turns=8, mob_level=1, start_hp_pct=1.0, hp_min_pct=1.0,
        total_damage_taken=0, max_hp=100, only_basic_attack=False, only_skills=False,
    )
    base.update(kwargs)
    return BattleReport(**base)


async def _unlocked(db, character, trial_id: str) -> bool:
    states = await trial_service.get_trial_states(db, character)
    return next(s for s in states if s.trial.id == trial_id).unlocked


async def _progress(db, character, trial_id: str) -> int:
    states = await trial_service.get_trial_states(db, character)
    return next(s for s in states if s.trial.id == trial_id).progress


def test_trial_defs_loaded() -> None:
    assert len(trial_service.trial_defs_for("guardian")) == 14
    assert trial_service.trial_def("guardian_bulwark").condition_type == "survive_hp_floor"


async def test_win_count_never_below_hp(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.6))
        assert not await _unlocked(db_session, character, "guardian_sturdy_armor")
    unlocked = await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.6))
    assert "guardian_sturdy_armor" in unlocked
    progress_before = await _progress(db_session, character, "guardian_sturdy_armor")
    await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.6))
    assert await _progress(db_session, character, "guardian_sturdy_armor") == progress_before  # завершено, не растёт


async def test_win_count_never_below_hp_not_satisfied_when_dropped_low(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.3))
    assert await _progress(db_session, character, "guardian_sturdy_armor") == 0


async def test_survive_hp_floor_single_shot(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    unlocked = await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.05))
    assert "guardian_bulwark" in unlocked


async def test_defeat_higher_level(db_session, make_character) -> None:
    character = await make_character(level=20, subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(mob_level=15))
    assert not await _unlocked(db_session, character, "guardian_reflection")
    unlocked = await trial_service.record_battle(db_session, character, _report(mob_level=25))
    assert "guardian_reflection" in unlocked


async def test_win_streak_start_hp_below_resets_on_unmet(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    assert await _progress(db_session, character, "guardian_resilience") == 2

    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.9))
    assert await _progress(db_session, character, "guardian_resilience") == 0

    for _ in range(2):
        await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    unlocked = await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    assert "guardian_resilience" in unlocked


async def test_win_streak_start_hp_below_resets_on_defeat(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.4))
    await trial_service.record_defeat(db_session, character)
    assert await _progress(db_session, character, "guardian_resilience") == 0


async def test_kill_count_in_ring(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(mob_level=10))  # вне кольца
    assert await _progress(db_session, character, "guardian_command") == 0
    await trial_service.record_battle(db_session, character, _report(mob_level=20))  # в кольце 16-30
    assert await _progress(db_session, character, "guardian_command") == 1


async def test_win_count_control_each_fight(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(control_landed=0))
    assert await _progress(db_session, character, "guardian_provoker_mark") == 0
    await trial_service.record_battle(db_session, character, _report(control_landed=2))
    assert await _progress(db_session, character, "guardian_provoker_mark") == 1


async def test_win_min_turns(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(turns=10))
    assert not await _unlocked(db_session, character, "guardian_unyielding")
    unlocked = await trial_service.record_battle(db_session, character, _report(turns=15))
    assert "guardian_unyielding" in unlocked


async def test_win_count_no_crit_taken(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(crit_taken=True))
    assert await _progress(db_session, character, "guardian_guard") == 0
    await trial_service.record_battle(db_session, character, _report(crit_taken=False))
    assert await _progress(db_session, character, "guardian_guard") == 1


async def test_event_choice_count(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_event_choice(db_session, character, "wounded_wanderer", "help")
    await trial_service.record_event_choice(db_session, character, "wounded_wanderer", "leave")  # не совпадает
    await trial_service.record_event_choice(db_session, character, "ash_altar", "help")  # не совпадает
    assert await _progress(db_session, character, "guardian_allys_shield") == 1
    await trial_service.record_event_choice(db_session, character, "wounded_wanderer", "help")
    unlocked = await trial_service.record_event_choice(db_session, character, "wounded_wanderer", "help")
    assert "guardian_allys_shield" in unlocked


async def test_win_streak_no_rest_resets_on_rest(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report())
    await trial_service.record_battle(db_session, character, _report())
    assert await _progress(db_session, character, "guardian_vital_block") == 2

    await trial_service.record_rest(db_session, character)
    assert await _progress(db_session, character, "guardian_vital_block") == 0

    for _ in range(2):
        await trial_service.record_battle(db_session, character, _report())
    unlocked = await trial_service.record_battle(db_session, character, _report())
    assert "guardian_vital_block" in unlocked


async def test_win_streak_no_rest_resets_on_defeat(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report())
    await trial_service.record_defeat(db_session, character)
    assert await _progress(db_session, character, "guardian_vital_block") == 0


async def test_reach_location_win(db_session, character_at) -> None:
    # (0,1) детерминированно хэшируется в ridge_redoubt (см. game/world/location_types.py)
    character = await character_at(0, 1, subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(won=False))
    assert not await _unlocked(db_session, character, "guardian_wall")
    unlocked = await trial_service.record_battle(db_session, character, _report(won=True))
    assert "guardian_wall" in unlocked


async def test_win_count_basic_attack_only(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(only_basic_attack=True))
    unlocked = await trial_service.record_battle(db_session, character, _report(only_basic_attack=True))
    assert "guardian_counterattack" in unlocked


async def test_win_start_hp_below_single(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.5))
    assert not await _unlocked(db_session, character, "guardian_retribution")
    unlocked = await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.2))
    assert "guardian_retribution" in unlocked


async def test_kill_in_max_turns(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    await trial_service.record_battle(db_session, character, _report(turns=5))
    assert not await _unlocked(db_session, character, "guardian_heavy_hand")
    unlocked = await trial_service.record_battle(db_session, character, _report(turns=3))
    assert "guardian_heavy_hand" in unlocked


# --- Условия, не завязанные на победу (crit_count, control_success_count, ...) ---


async def test_crit_count_progresses_regardless_of_outcome(db_session, make_character) -> None:
    character = await make_character(subclass="shadow_blade")
    await trial_service.record_battle(db_session, character, _report(won=False, crits_dealt=3))
    assert await _progress(db_session, character, "shadow_blade_deadly_precision") == 3


async def test_consecutive_crits_in_fight(db_session, make_character) -> None:
    character = await make_character(subclass="shadow_blade")
    unlocked = await trial_service.record_battle(
        db_session, character, _report(won=False, consecutive_crits=True)
    )
    assert "shadow_blade_bloodlust" in unlocked


async def test_control_success_count(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    await trial_service.record_battle(db_session, character, _report(won=False, control_landed=15))
    assert await _unlocked(db_session, character, "poisoner_hallucinogen")


async def test_skill_combo_streak_count(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(won=False, skill_combo_streak_count=1))
    unlocked = await trial_service.record_battle(
        db_session, character, _report(won=False, skill_combo_streak_count=1)
    )
    assert "poisoner_double_dose" in unlocked


async def test_all_elements_in_fight_count(db_session, make_character) -> None:
    character = await make_character(subclass="elementalist")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(won=False, all_elements_used=True))
    unlocked = await trial_service.record_battle(
        db_session, character, _report(won=False, all_elements_used=True)
    )
    assert "elementalist_universal_element" in unlocked


async def test_elemental_finisher_kill_count(db_session, make_character) -> None:
    character = await make_character(subclass="elementalist")
    report = _report(finisher_skill_id="elementalist_fire")
    for _ in range(14):
        await trial_service.record_battle(db_session, character, report)
    unlocked = await trial_service.record_battle(db_session, character, report)
    assert "elementalist_flame_power" in unlocked

    character2 = await make_character(subclass="elementalist")
    await trial_service.record_battle(
        db_session, character2, _report(finisher_skill_id="elementalist_ice")
    )
    assert await _progress(db_session, character2, "elementalist_flame_power") == 0


async def test_win_count_freeze_each_fight_and_control_freeze_count(db_session, make_character) -> None:
    character = await make_character(subclass="elementalist")
    await trial_service.record_battle(db_session, character, _report(won=False, control_landed=15))
    assert await _unlocked(db_session, character, "elementalist_deep_freeze")

    character2 = await make_character(subclass="elementalist")
    for _ in range(4):
        await trial_service.record_battle(db_session, character2, _report(control_landed=1))
    unlocked = await trial_service.record_battle(db_session, character2, _report(control_landed=1))
    assert "elementalist_numbness" in unlocked


async def test_crit_finisher_count(db_session, make_character) -> None:
    character = await make_character(subclass="blood_knight")
    for _ in range(4):
        await trial_service.record_battle(db_session, character, _report(finisher_is_crit=True))
    unlocked = await trial_service.record_battle(db_session, character, _report(finisher_is_crit=True))
    assert "blood_knight_vein_rupture" in unlocked


async def test_skill_finisher_count(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(finisher_skill_id="poison_lash"))
    unlocked = await trial_service.record_battle(
        db_session, character, _report(finisher_skill_id="poison_lash")
    )
    assert "poisoner_toxic_burst" in unlocked


async def test_win_damage_taken_exceeds_maxhp(db_session, make_character) -> None:
    character = await make_character(subclass="blood_knight")
    await trial_service.record_battle(db_session, character, _report(total_damage_taken=50, max_hp=100))
    assert not await _unlocked(db_session, character, "blood_knight_eternal_hunger")
    unlocked = await trial_service.record_battle(
        db_session, character, _report(total_damage_taken=150, max_hp=100)
    )
    assert "blood_knight_eternal_hunger" in unlocked


async def test_kill_count_max_turns_each(db_session, make_character) -> None:
    character = await make_character(subclass="blood_knight")
    for _ in range(4):
        await trial_service.record_battle(db_session, character, _report(turns=4))
    unlocked = await trial_service.record_battle(db_session, character, _report(turns=4))
    assert "blood_knight_blood_rage" in unlocked


async def test_walk_cells_no_combat_and_reset(db_session, make_character) -> None:
    character = await make_character(subclass="shadow_blade")
    for _ in range(19):
        await trial_service.record_cell_moved(db_session, character)
    assert await _progress(db_session, character, "shadow_blade_hunters_solitude") == 19

    await trial_service.record_combat_started(db_session, character)
    assert await _progress(db_session, character, "shadow_blade_hunters_solitude") == 0

    for _ in range(19):
        await trial_service.record_cell_moved(db_session, character)
    unlocked = await trial_service.record_cell_moved(db_session, character)
    assert "shadow_blade_hunters_solitude" in unlocked


async def test_collect_trophy_count(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    await trial_service.record_trophies(db_session, character, {"blood_shard": 4})
    assert await _progress(db_session, character, "poisoner_toxicology") == 4
    unlocked = await trial_service.record_trophies(db_session, character, {"blood_shard": 6, "ash_dust": 99})
    assert "poisoner_toxicology" in unlocked


async def test_win_count_dropped_below_hp(db_session, make_character) -> None:
    character = await make_character(subclass="blood_knight")
    await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.8))
    assert await _progress(db_session, character, "blood_knight_thirst") == 0
    for _ in range(3):
        await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.3))
    assert await _unlocked(db_session, character, "blood_knight_thirst")


async def test_win_count_start_hp_below(db_session, make_character) -> None:
    character = await make_character(subclass="dark_mystic")
    for _ in range(4):
        await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.5))
    unlocked = await trial_service.record_battle(db_session, character, _report(start_hp_pct=0.5))
    assert "dark_mystic_blood_pact_plus" in unlocked


async def test_win_no_hp_below_single(db_session, make_character) -> None:
    character = await make_character(subclass="shadow_blade")
    await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.8))
    assert not await _unlocked(db_session, character, "shadow_blade_slip_away")
    unlocked = await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.95))
    assert "shadow_blade_slip_away" in unlocked


async def test_win_count_skills_only(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(only_skills=True))
    unlocked = await trial_service.record_battle(db_session, character, _report(only_skills=True))
    assert "poisoner_lingering_poison" in unlocked


async def test_win_count_debuff_skill_each_fight(db_session, make_character) -> None:
    character = await make_character(subclass="poisoner")
    for _ in range(9):
        await trial_service.record_battle(db_session, character, _report(debuff_skill_used=True))
    unlocked = await trial_service.record_battle(db_session, character, _report(debuff_skill_used=True))
    assert "poisoner_toxic_blood" in unlocked


async def test_unlocked_buff_ids_and_get_trial_states(db_session, make_character) -> None:
    character = await make_character(subclass="guardian")
    assert await trial_service.unlocked_buff_ids(db_session, character.id) == set()
    await trial_service.record_battle(db_session, character, _report(hp_min_pct=0.05))  # guardian_bulwark
    assert "guardian_bulwark" in await trial_service.unlocked_buff_ids(db_session, character.id)

    states = await trial_service.get_trial_states(db_session, character)
    assert len(states) == 14
    bulwark = next(s for s in states if s.trial.id == "guardian_bulwark")
    assert bulwark.unlocked and bulwark.progress == 1 and bulwark.target == 1


async def test_get_trial_states_empty_without_subclass(db_session, make_character) -> None:
    character = await make_character()
    assert await trial_service.get_trial_states(db_session, character) == []
    assert await trial_service.record_battle(db_session, character, _report()) == []
