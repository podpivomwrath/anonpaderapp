"""Патч 27: services/admin_service.py — статистика, поиск/карточка, действия
(каждое логируется), бан, лог смертей, репорты багов."""

import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.combat import balance_config as bc
from models import AdminAction, Character, CharacterDeath, CharacterStats, User
from services import admin_service, experience_service, item_service, movement_service, trophy_service


# --- Журнал / лог смертей ---


async def test_log_action_persists_row(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.log_action(
        db_session, 999, "grant_xp", character.id, old_value={"a": 1}, new_value={"a": 2}
    )
    rows = (await db_session.execute(select(AdminAction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].admin_vk_id == 999
    assert rows[0].action_type == "grant_xp"


async def test_log_death_persists_position_and_cause(db_session, character_at) -> None:
    character = await character_at(10, -5)
    await admin_service.log_death(db_session, character, "pve")
    rows = (await db_session.execute(select(CharacterDeath))).scalars().all()
    assert len(rows) == 1
    assert (rows[0].pos_x, rows[0].pos_y, rows[0].cause) == (10, -5, "pve")


# --- Обзор ---


async def test_overview_counts_finished_characters(db_session, make_character) -> None:
    await make_character()
    await make_character()
    stats = await admin_service.overview_stats(db_session)
    assert stats.players["total_characters"] == 2
    assert stats.players["stuck_onboarding"] == 0


async def test_overview_excludes_unfinished_onboarding(db_session, make_character) -> None:
    character = await make_character()
    character.creation_state = "nickname_input"
    stats = await admin_service.overview_stats(db_session)
    assert stats.players["total_characters"] == 0
    assert stats.players["stuck_onboarding"] == 1


async def test_overview_deaths_by_zone_uses_position(db_session, character_at) -> None:
    character = await character_at(50, 50)  # зона 1-15 (внешнее кольцо)
    await admin_service.log_death(db_session, character, "pve")
    stats = await admin_service.overview_stats(db_session)
    assert stats.combat["deaths_24h"] == 1
    assert stats.combat["deaths_by_zone_24h"] == {"1-15": 1}


# --- Поиск и карточка ---


async def test_search_by_name_substring(db_session, make_character) -> None:
    await make_character()  # "Тестовый#1"
    results = await admin_service.search_characters(db_session, "естов")
    assert len(results) == 1


async def test_search_by_vk_id(db_session, make_character) -> None:
    character = await make_character()
    user = await db_session.get(User, character.user_id)
    results = await admin_service.search_characters(db_session, str(user.vk_id))
    assert len(results) == 1
    assert results[0].id == character.id


async def test_search_empty_query_returns_nothing(db_session, make_character) -> None:
    await make_character()
    assert await admin_service.search_characters(db_session, "   ") == []


async def test_player_card_contains_core_fields(db_session, character_at) -> None:
    character = await character_at(1, 2, farm=50, donate=5)
    card = await admin_service.player_card(db_session, character.id)
    assert card["name"] == character.name
    assert card["gold"] == 50
    assert card["gems"] == 5
    assert card["pos_x"] == 1 and card["pos_y"] == 2
    assert card["is_banned"] is False


async def test_player_card_missing_character_returns_none(db_session) -> None:
    assert await admin_service.player_card(db_session, 999999) is None


# --- Действия (каждое логируется) ---


async def test_grant_currency_deposits_and_logs(db_session, make_character) -> None:
    character = await make_character(farm=10)
    wallet = await admin_service.grant_currency(db_session, 1, character, "farm", 5)
    assert wallet.farm_currency == 15
    actions = await admin_service.action_journal(db_session)
    assert actions[0].action_type == "grant_currency"


async def test_grant_currency_clamps_at_zero_when_taking(db_session, make_character) -> None:
    character = await make_character(farm=3)
    wallet = await admin_service.grant_currency(db_session, 1, character, "farm", -10)
    assert wallet.farm_currency == 0


async def test_grant_trophy_adds_to_stock(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.grant_trophy(db_session, 1, character, "ash_dust", 4)
    stock = await trophy_service.get_stock(db_session, character.id)
    assert stock[0][1] == 4


async def test_grant_xp_applies_levelup(db_session, make_character) -> None:
    character = await make_character(level=1, experience=0)
    result = await admin_service.grant_xp(db_session, 1, character, experience_service.xp_to_next(1) + 5)
    assert result.levels_gained >= 1
    assert character.level == 1 + result.levels_gained


async def test_grant_item_adds_to_inventory(db_session, make_character) -> None:
    character = await make_character()
    item = await admin_service.grant_item(db_session, 1, character, 10, random.Random(1))
    inventory = await item_service.get_inventory(db_session, character.id)
    assert any(i.id == item.id for i, _equipped in inventory)


async def test_set_level_resets_experience_and_heals(db_session, make_character) -> None:
    character = await make_character(level=5, experience=999)
    character.current_hp = 1
    await admin_service.set_level(db_session, 1, character, 10)
    assert character.level == 10
    assert character.experience == 0
    assert character.current_hp is None  # NULL = полное HP


async def test_set_level_clamps_to_bounds(db_session, make_character) -> None:
    character = await make_character(level=5)
    await admin_service.set_level(db_session, 1, character, 99999)
    assert character.level == bc.MAX_LEVEL

    await admin_service.set_level(db_session, 1, character, -5)
    assert character.level == 1


async def test_teleport_moves_and_cancels_travel(db_session, character_at) -> None:
    character = await character_at(0, 0)
    movement_service.start_travel(character, 5, 5)
    await admin_service.teleport(db_session, 1, character, 20, -20)
    assert (character.pos_x, character.pos_y) == (20, -20)
    assert not movement_service.is_traveling(character)


async def test_teleport_out_of_bounds_raises(db_session, character_at) -> None:
    character = await character_at(0, 0)
    with pytest.raises(ValueError):
        await admin_service.teleport(db_session, 1, character, 999, 0)


async def test_restore_hp_clears_hp_and_respawn(db_session, make_character) -> None:
    character = await make_character()
    character.current_hp = 1
    character.respawn_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await admin_service.restore_hp(db_session, 1, character)
    assert character.current_hp is None
    assert character.respawn_at is None


async def test_reset_activity_db_cancels_movement(db_session, character_at) -> None:
    character = await character_at(0, 0)
    movement_service.start_travel(character, 1, 1)
    await admin_service.reset_activity_db(db_session, character)
    assert not movement_service.is_traveling(character)


async def test_reset_stats_returns_to_starting_allocation(db_session, make_character) -> None:
    character = await make_character(base_class="warrior")
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    stats.strength = 40
    stats.unspent_points = 0
    await admin_service.reset_stats(db_session, 1, character)
    start = bc.STARTING_STATS["warrior"]
    assert stats.strength == start["STR"]
    assert stats.unspent_points > 0  # разница вернулась в пул


async def test_ban_and_unban_roundtrip(db_session, make_character) -> None:
    character = await make_character()
    assert not admin_service.is_ban_active(character)

    await admin_service.ban(db_session, 1, character, "спам")
    assert character.is_banned is True
    assert character.ban_reason == "спам"
    assert admin_service.is_ban_active(character)

    await admin_service.unban(db_session, 1, character)
    assert character.is_banned is False
    assert not admin_service.is_ban_active(character)


async def test_is_ban_active_respects_expiry() -> None:
    character = Character(user_id=1, name="x", base_class="warrior")
    character.is_banned = True
    character.banned_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert not admin_service.is_ban_active(character)

    character.banned_until = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert admin_service.is_ban_active(character)

    character.banned_until = None
    assert admin_service.is_ban_active(character)  # бессрочный


async def test_action_journal_orders_newest_first(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.log_action(db_session, 1, "a", character.id)
    await admin_service.log_action(db_session, 1, "b", character.id)
    actions = await admin_service.action_journal(db_session)
    assert [a.action_type for a in actions] == ["b", "a"]


# --- Репорты багов ---


async def test_create_and_list_bug_reports(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.create_bug_report(db_session, character.id, "текст", {"level": 5})
    reports = await admin_service.list_bug_reports(db_session)
    assert len(reports) == 1
    assert reports[0].text == "текст"
    assert reports[0].status == "new"


async def test_bug_reports_since_counts_recent_only(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.create_bug_report(db_session, character.id, "текст", {})
    since_future = datetime.now(timezone.utc) + timedelta(hours=1)
    since_past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await admin_service.bug_reports_since(db_session, character.id, since_past) == 1
    assert await admin_service.bug_reports_since(db_session, character.id, since_future) == 0


async def test_set_bug_report_status_updates(db_session, make_character) -> None:
    character = await make_character()
    report = await admin_service.create_bug_report(db_session, character.id, "текст", {})
    updated = await admin_service.set_bug_report_status(db_session, report.id, "closed")
    assert updated.status == "closed"


async def test_set_bug_report_status_missing_returns_none(db_session) -> None:
    assert await admin_service.set_bug_report_status(db_session, 999999, "closed") is None


async def test_duplicate_bug_report_finds_identical_recent_text(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.create_bug_report(db_session, character.id, "не работает кнопка", {})
    since = datetime.now(timezone.utc) - timedelta(seconds=30)
    dup = await admin_service.duplicate_bug_report(db_session, character.id, "не работает кнопка", since)
    assert dup is not None


async def test_duplicate_bug_report_ignores_different_text(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.create_bug_report(db_session, character.id, "не работает кнопка", {})
    since = datetime.now(timezone.utc) - timedelta(seconds=30)
    dup = await admin_service.duplicate_bug_report(db_session, character.id, "другой текст", since)
    assert dup is None


async def test_duplicate_bug_report_ignores_too_old(db_session, make_character) -> None:
    character = await make_character()
    await admin_service.create_bug_report(db_session, character.id, "текст", {})
    since_future = datetime.now(timezone.utc) + timedelta(hours=1)
    dup = await admin_service.duplicate_bug_report(db_session, character.id, "текст", since_future)
    assert dup is None
