"""Ежедневные задания, стрики, награды за вход (патч 23)."""

from datetime import datetime, timedelta, timezone

import pytest

from game.combat.battle_report import BattleReport
from game.economy import dailies_config as dc
from models import Character, CharacterDaily
from services import daily_service, elixir_service, wallet_service


def _report(**kwargs) -> BattleReport:
    base = dict(
        won=True, turns=3, mob_level=1, start_hp_pct=1.0, hp_min_pct=1.0,
        total_damage_taken=0, max_hp=100, only_basic_attack=False, only_skills=True,
    )
    base.update(kwargs)
    return BattleReport(**base)


async def _add_quest(db, character: Character, quest_id: str, progress: int = 0) -> CharacterDaily:
    row = CharacterDaily(
        character_id=character.id, quest_id=quest_id, progress=progress, completed=False,
        date=daily_service.today_msk(),
    )
    db.add(row)
    await db.flush()
    return row


def test_daily_reward_xp_scales_as_share_of_xp_to_next() -> None:
    """Патч 31, п.3: опыт за ежедневку — доля xp_to_next(level), а не
    xp_per_mob(level) — раньше линейный рост xp_per_mob против почти
    квадратичного xp_to_next (XP_EXP=1.95) обесценивал ежедневки к концу игры."""
    from services.experience_service import xp_to_next

    for level in (1, 10, 50, 90):
        xp, gold = dc.daily_reward(level)
        assert xp == int(xp_to_next(level) * dc.DAILY_XP_SHARE)
        assert gold == dc.DAILY_GOLD_BASE + dc.DAILY_GOLD_PER_LEVEL * level


def test_daily_reward_xp_share_consistent_across_levels() -> None:
    """Доля прогресса до след. уровня, которую даёт одна ежедневка, должна
    быть одинаковой на низком и высоком уровне (это и есть цель патча)."""
    from services.experience_service import xp_to_next

    shares = {level: dc.daily_reward(level)[0] / xp_to_next(level) for level in (5, 55)}
    assert shares[5] == pytest.approx(shares[55], rel=0.01)


async def test_first_rollover_sets_streak_to_1_and_assigns_dailies(db_session, make_character) -> None:
    character = await make_character(level=5)
    assert character.last_login_date is None
    notice = await daily_service.ensure_day_rollover(db_session, character)
    assert character.login_streak == 1
    assert character.login_cycle_day == 1
    assert character.last_login_date == daily_service.today_msk()
    assert notice is not None  # день 1 цикла даёт награду
    overview = await daily_service.get_dailies_overview(db_session, character)
    assert len(overview.quests) == dc.DAILY_QUEST_COUNT


async def test_same_day_rollover_is_noop(db_session, make_character) -> None:
    character = await make_character(level=5)
    await daily_service.ensure_day_rollover(db_session, character)
    streak_after_first = character.login_streak
    notice = await daily_service.ensure_day_rollover(db_session, character)
    assert notice is None
    assert character.login_streak == streak_after_first


async def test_consecutive_day_increments_streak(db_session, make_character) -> None:
    character = await make_character(level=5)
    yesterday = daily_service.today_msk() - timedelta(days=1)
    character.last_login_date = yesterday
    character.login_streak = 3
    character.login_cycle_day = 3
    await daily_service.ensure_day_rollover(db_session, character)
    assert character.login_streak == 4
    assert character.login_cycle_day == 4


async def test_gap_resets_login_streak_with_notice(db_session, make_character) -> None:
    character = await make_character(level=5)
    character.last_login_date = daily_service.today_msk() - timedelta(days=3)
    character.login_streak = 10
    character.login_cycle_day = 10
    notice = await daily_service.ensure_day_rollover(db_session, character)
    assert character.login_streak == 1
    assert character.login_cycle_day == 1
    assert notice is not None
    assert any("обнулён" in line for line in notice.lines)


async def test_login_cycle_wraps_after_14_days(db_session, make_character) -> None:
    character = await make_character(level=5)
    character.last_login_date = daily_service.today_msk() - timedelta(days=1)
    character.login_streak = 14
    character.login_cycle_day = 14
    await daily_service.ensure_day_rollover(db_session, character)
    assert character.login_streak == 15
    assert character.login_cycle_day == 1  # цикл начался заново


async def test_login_cycle_day_14_grants_gems(db_session, make_character) -> None:
    character = await make_character(level=5)
    character.last_login_date = daily_service.today_msk() - timedelta(days=1)
    character.login_streak = 13
    character.login_cycle_day = 13
    await daily_service.ensure_day_rollover(db_session, character)
    assert character.login_cycle_day == 14
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.donate_currency == dc.LOGIN_CYCLE_REWARDS[14]["gems"]


async def test_daily_streak_resets_if_no_completion_yesterday(db_session, make_character) -> None:
    character = await make_character(level=5)
    character.last_login_date = daily_service.today_msk() - timedelta(days=1)
    character.login_streak = 5
    character.login_cycle_day = 5
    character.daily_streak = 7
    character.last_daily_completed_date = daily_service.today_msk() - timedelta(days=5)
    await daily_service.ensure_day_rollover(db_session, character)
    assert character.daily_streak == 0


async def test_daily_streak_survives_if_completed_yesterday(db_session, make_character) -> None:
    character = await make_character(level=5)
    character.last_login_date = daily_service.today_msk() - timedelta(days=1)
    character.login_streak = 5
    character.login_cycle_day = 5
    character.daily_streak = 7
    character.last_daily_completed_date = daily_service.today_msk() - timedelta(days=1)
    await daily_service.ensure_day_rollover(db_session, character)
    assert character.daily_streak == 7  # не сброшен, просто ещё не увеличен сегодня


async def test_record_battle_completes_kill_any_and_grants_reward(db_session, make_character) -> None:
    character = await make_character(level=10, experience=0)
    row = await _add_quest(db_session, character, "hunt")
    target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    row.progress = target - 1
    await db_session.flush()

    result = await daily_service.record_battle(db_session, character, _report(won=True))
    assert len(result.completed) == 1
    assert result.completed[0].quest_title == "Охота"
    wallet = await wallet_service.get_wallet(db_session, character.id)
    # >=, не ==: первое выполненное задание за день = первый день стрика ->
    # Пепельный ларец (патч 24) тоже открывается и может добавить своё золото.
    assert wallet.farm_currency >= result.completed[0].gold
    assert character.experience == result.completed[0].xp
    assert row.completed is True


async def test_record_battle_does_not_double_complete(db_session, make_character) -> None:
    character = await make_character(level=10)
    row = await _add_quest(db_session, character, "hunt")
    target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    row.progress = target
    row.completed = True
    await db_session.flush()

    result = await daily_service.record_battle(db_session, character, _report(won=True))
    assert result.completed == []


async def test_record_trophies_tracks_trophy_any_and_rare(db_session, make_character) -> None:
    character = await make_character(level=1)
    any_row = await _add_quest(db_session, character, "collector")
    rare_row = await _add_quest(db_session, character, "diligent")

    await daily_service.record_trophies(db_session, character, {"ash_dust": 3, "taint_clot": 2})
    assert any_row.progress == 5  # любая градация считается
    assert rare_row.progress == 2  # только 🔵 и выше (не ash_dust)


async def test_kill_streak_no_rest_resets_on_rest(db_session, make_character) -> None:
    character = await make_character(level=1)
    row = await _add_quest(db_session, character, "endurance")
    await daily_service.record_battle(db_session, character, _report(won=True))
    assert row.progress == 1
    await daily_service.record_rest(db_session, character)
    assert row.progress == 0


async def test_kill_streak_no_rest_resets_on_defeat(db_session, make_character) -> None:
    character = await make_character(level=1)
    row = await _add_quest(db_session, character, "endurance")
    await daily_service.record_battle(db_session, character, _report(won=True))
    assert row.progress == 1
    await daily_service.record_defeat(db_session, character)
    assert row.progress == 0


async def test_low_hp_survive_requires_win_and_low_hp(db_session, make_character) -> None:
    character = await make_character(level=1)
    row = await _add_quest(db_session, character, "survivor")
    await daily_service.record_battle(db_session, character, _report(won=True, hp_min_pct=0.9))
    assert row.progress == 0
    await daily_service.record_battle(db_session, character, _report(won=True, hp_min_pct=0.1))
    assert row.progress == 1


async def test_skill_only_win_requires_only_skills(db_session, make_character) -> None:
    character = await make_character(level=1)
    row = await _add_quest(db_session, character, "blood_trial")
    await daily_service.record_battle(db_session, character, _report(won=True, only_skills=False))
    assert row.progress == 0
    await daily_service.record_battle(db_session, character, _report(won=True, only_skills=True))
    assert row.progress == 1


async def test_sell_gold_tracks_amount(db_session, make_character) -> None:
    character = await make_character(level=1)
    row = await _add_quest(db_session, character, "fence")
    await daily_service.record_sell_gold(db_session, character, 300)
    assert row.progress == 300


async def test_pvp_quest_excluded_below_min_level(db_session, make_character) -> None:
    low_level = await make_character(level=1)
    high_level = await make_character(level=dc.PVP_QUEST_MIN_LEVEL)
    low_pool = daily_service._eligible_pool(low_level)
    high_pool = daily_service._eligible_pool(high_level)
    assert "marked_hunter" not in {q.id for q in low_pool}
    assert "marked_hunter" in {q.id for q in high_pool}


async def test_daily_streak_milestone_grants_reward(db_session, make_character) -> None:
    character = await make_character(level=1)
    character.daily_streak = 6  # следующая завершённая ежедневка станет 7-й
    row = await _add_quest(db_session, character, "hunt")
    target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    row.progress = target - 1
    await db_session.flush()

    result = await daily_service.record_battle(db_session, character, _report(won=True))
    assert character.daily_streak == 7
    assert result.streak_notice is not None
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency >= dc.STREAK_MILESTONES[7]["gold"]


async def test_daily_streak_milestone_365_unlocks_title(db_session, make_character) -> None:
    character = await make_character(level=1)
    character.daily_streak = 364
    row = await _add_quest(db_session, character, "hunt")
    target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    row.progress = target - 1
    await db_session.flush()

    await daily_service.record_battle(db_session, character, _report(won=True))
    assert character.daily_streak == 365
    assert character.active_title_id == "relentless"
    assert daily_service.title_name(character) == "Неотступный"


async def test_grant_reward_only_once_per_day_across_multiple_completions(db_session, make_character) -> None:
    character = await make_character(level=1)
    hunt = await _add_quest(db_session, character, "hunt")
    wanderer = await _add_quest(db_session, character, "wanderer")
    hunt_target = dc.scaled_target(daily_service.quest_def("hunt").base_target, character.level)
    wanderer_target = dc.scaled_target(daily_service.quest_def("wanderer").base_target, character.level)
    hunt.progress = hunt_target - 1
    wanderer.progress = wanderer_target - 1
    await db_session.flush()

    await daily_service.record_battle(db_session, character, _report(won=True))
    assert character.daily_streak == 1
    await daily_service.record_cell_moved(db_session, character)
    assert character.daily_streak == 1  # вторая ежедневка в тот же день не увеличивает стрик повторно


async def test_elixir_service_grant_adds_without_charging_gold(db_session, make_character) -> None:
    character = await make_character(level=1, farm=0)
    await elixir_service.grant(db_session, character.id, "heal_small", 3)
    stock = await elixir_service.get_stock(db_session, character.id)
    counts = {d.id: count for d, count in stock}
    assert counts["heal_small"] == 3
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 0
