"""Метка Хранителя — премиум-аккаунт (патч 50): is_premium/extend/уведомления
и семь бонусов, единая точка проверки — services/premium_service.py."""

import random
from datetime import datetime, timedelta, timezone

import pytest

from game.economy import dailies_config as dc
from game.economy import item_gen
from game.economy import premium_config as pc
from game.economy import raid_key_config as rc
from services import daily_service, experience_service, premium_service, preset_service, raid_key_service
from services.item_service import rarities


class FixedRng(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def random(self) -> float:
        return self._value


# --- is_premium / badge ---


async def test_is_premium_false_when_never_activated(make_character) -> None:
    character = await make_character()
    assert premium_service.is_premium(character) is False
    assert premium_service.badge(character) == ""


async def test_is_premium_true_within_period(make_character) -> None:
    character = await make_character()
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=5)
    assert premium_service.is_premium(character) is True
    assert premium_service.badge(character) == f"{pc.PREMIUM_BADGE} "


async def test_is_premium_false_after_expiry(make_character) -> None:
    character = await make_character()
    character.premium_until = datetime.now(timezone.utc) - timedelta(hours=1)
    assert premium_service.is_premium(character) is False


# --- extend: суммирование срока ---


async def test_extend_from_zero_sets_duration(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    premium_service.extend(character, 30, now=now)
    assert character.premium_until == now + timedelta(days=30)


async def test_extend_sums_with_remaining_active_period(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now + timedelta(days=5)
    premium_service.extend(character, 30, now=now)
    assert character.premium_until == now + timedelta(days=35)


async def test_extend_after_expiry_starts_from_now(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now - timedelta(days=10)
    premium_service.extend(character, 7, now=now)
    assert character.premium_until == now + timedelta(days=7)


async def test_extend_resets_notification_flags(make_character) -> None:
    character = await make_character()
    character.premium_warn_sent = True
    character.premium_expire_notified = True
    premium_service.extend(character, 3)
    assert character.premium_warn_sent is False
    assert character.premium_expire_notified is False


# --- check_expiry_notice: идемпотентные разовые уведомления ---


async def test_check_expiry_notice_none_when_far_from_expiry(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now + timedelta(days=10)
    assert premium_service.check_expiry_notice(character, now=now) is None


async def test_check_expiry_notice_warns_once(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now + timedelta(hours=12)
    line = premium_service.check_expiry_notice(character, now=now)
    assert line == pc.EXPIRY_WARNING_TEXT
    assert character.premium_warn_sent is True
    assert premium_service.check_expiry_notice(character, now=now) is None


async def test_check_expiry_notice_fires_once_on_expiry(make_character) -> None:
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now - timedelta(minutes=1)
    line = premium_service.check_expiry_notice(character, now=now)
    assert line == pc.EXPIRED_TEXT
    assert character.premium_expire_notified is True
    assert premium_service.check_expiry_notice(character, now=now) is None


async def test_check_expiry_notice_none_when_never_activated(make_character) -> None:
    character = await make_character()
    assert premium_service.check_expiry_notice(character) is None


# --- Бонус 1: +50% опыта ---


async def test_xp_multiplier_applied_for_premium(make_character, db_session) -> None:
    from sqlalchemy import select

    from models import CharacterStats

    character = await make_character(level=5)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    before = character.experience
    experience_service.add_experience(character, stats, 100)
    assert character.experience - before == round(100 * pc.PREMIUM_XP_MULTIPLIER)


async def test_xp_multiplier_not_applied_without_premium(make_character, db_session) -> None:
    from sqlalchemy import select

    from models import CharacterStats

    character = await make_character(level=5)
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    before = character.experience
    experience_service.add_experience(character, stats, 100)
    assert character.experience - before == 100


async def test_xp_multiplier_exempted_for_admin_grant(make_character, db_session) -> None:
    from sqlalchemy import select

    from models import CharacterStats

    character = await make_character(level=5)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    stats = await db_session.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    before = character.experience
    experience_service.add_experience(character, stats, 100, apply_premium=False)
    assert character.experience - before == 100


# --- Бонус 2: апгрейд редкости лута ---


def test_maybe_upgrade_rarity_bumps_one_step_on_success() -> None:
    r = rarities()
    ids = list(r.keys())
    result = item_gen.maybe_upgrade_rarity(ids[0], r, FixedRng(0.0), pc.PREMIUM_RARITY_UPGRADE_CHANCE)
    assert result == ids[1]


def test_maybe_upgrade_rarity_no_change_on_miss() -> None:
    r = rarities()
    ids = list(r.keys())
    result = item_gen.maybe_upgrade_rarity(ids[0], r, FixedRng(0.999), pc.PREMIUM_RARITY_UPGRADE_CHANCE)
    assert result == ids[0]


def test_maybe_upgrade_rarity_caps_at_legendary() -> None:
    r = rarities()
    ids = list(r.keys())
    result = item_gen.maybe_upgrade_rarity(ids[-1], r, FixedRng(0.0), pc.PREMIUM_RARITY_UPGRADE_CHANCE)
    assert result == ids[-1]


# --- Бонус 3: кап ключей рейда 4 вместо 2, ключи не отбираются ---


async def test_raid_key_cap_is_higher_for_premium(make_character, db_session) -> None:
    character = await make_character()
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    character.raid_keys = rc.RAID_KEY_CAP  # 2 — обычный кап уже достигнут
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is True
    assert character.raid_keys == rc.RAID_KEY_CAP + 1


async def test_raid_key_cap_stops_at_premium_cap(make_character, db_session) -> None:
    character = await make_character()
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    character.raid_keys = rc.RAID_KEY_CAP_PREMIUM
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is False
    assert character.raid_keys == rc.RAID_KEY_CAP_PREMIUM


async def test_raid_keys_not_stripped_after_expiry_but_no_new_drops(make_character, db_session) -> None:
    character = await make_character()
    character.raid_keys = 4  # выше обычного капа — остался от истёкшего премиума
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is False
    assert character.raid_keys == 4  # не отобрали


async def test_raid_keys_resume_dropping_once_below_base_cap(make_character, db_session) -> None:
    character = await make_character()
    character.raid_keys = rc.RAID_KEY_CAP - 1
    dropped = await raid_key_service.maybe_grant(db_session, character, FixedRng(0.0))
    assert dropped is True
    assert character.raid_keys == rc.RAID_KEY_CAP


# --- Бонус 4: +1 слот пресета, не удаляется на истечении ---


async def test_effective_preset_slots_bonus_for_premium(make_character) -> None:
    character = await make_character()
    character.preset_slots = 1
    no_bonus = preset_service.effective_preset_slots(character)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    with_bonus = preset_service.effective_preset_slots(character)
    assert no_bonus == 1
    assert with_bonus == 2


async def test_second_preset_requires_premium_bonus_slot(make_character, db_session) -> None:
    from game.combat import balance_config as bc
    from game.content_loader import load_content
    from models import CharacterUnlockedBuff
    from services.preset_service import PresetValidationError, save_preset

    catalog = load_content().buffs
    first_set = ["guardian_heavy_hand", "guardian_bulwark", "guardian_command"]
    second_set = ["guardian_heavy_hand", "guardian_reflection", "guardian_provoker_mark"]

    character = await make_character(farm=bc.PRESET_CHANGE_COST_FARM * 2, subclass="guardian")
    for buff_id in set(first_set) | set(second_set):
        db_session.add(CharacterUnlockedBuff(character_id=character.id, buff_id=buff_id))
    await db_session.flush()

    await save_preset(db_session, character, "Танк", first_set, catalog)
    # preset_slots=1 (стартовый), без премиума второй пресет недоступен
    with pytest.raises(PresetValidationError):
        await save_preset(db_session, character, "ДД", second_set, catalog)

    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    second = await save_preset(db_session, character, "ДД", second_set, catalog)
    assert second.buff_ids == second_set


async def test_preset_switch_blocked_when_beyond_effective_slots_after_expiry(make_character, db_session) -> None:
    from game.combat import balance_config as bc
    from game.content_loader import load_content
    from models import CharacterUnlockedBuff
    from services.preset_service import PresetValidationError, save_preset, switch_active_preset

    catalog = load_content().buffs
    first_set = ["guardian_heavy_hand", "guardian_bulwark", "guardian_command"]
    second_set = ["guardian_heavy_hand", "guardian_reflection", "guardian_provoker_mark"]

    character = await make_character(farm=bc.PRESET_CHANGE_COST_FARM * 2, subclass="guardian")
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    for buff_id in set(first_set) | set(second_set):
        db_session.add(CharacterUnlockedBuff(character_id=character.id, buff_id=buff_id))
    await db_session.flush()

    first = await save_preset(db_session, character, "Танк", first_set, catalog)
    second = await save_preset(db_session, character, "ДД", second_set, catalog)  # за счёт бонусного слота

    character.premium_until = None  # премиум истёк — второй пресет не удалён, но недоступен для переключения
    with pytest.raises(PresetValidationError):
        await switch_active_preset(db_session, character, second.id)

    switched = await switch_active_preset(db_session, character, first.id)
    assert switched.id == first.id


# --- Бонус 6: 5 ежедневок вместо 3 ---


async def test_daily_quest_count_higher_for_premium(make_character, db_session, seed_quests) -> None:
    from datetime import date

    character = await make_character(level=20)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    today = date.today()
    await daily_service._assign_new_dailies(db_session, character, today)

    from sqlalchemy import func, select

    from models import CharacterDaily

    count = await db_session.scalar(
        select(func.count()).select_from(CharacterDaily).where(
            CharacterDaily.character_id == character.id, CharacterDaily.date == today,
        )
    )
    assert count == dc.DAILY_QUEST_COUNT_PREMIUM


async def test_daily_quest_count_normal_without_premium(make_character, db_session, seed_quests) -> None:
    from datetime import date

    character = await make_character(level=20)
    today = date.today()
    await daily_service._assign_new_dailies(db_session, character, today)

    from sqlalchemy import func, select

    from models import CharacterDaily

    count = await db_session.scalar(
        select(func.count()).select_from(CharacterDaily).where(
            CharacterDaily.character_id == character.id, CharacterDaily.date == today,
        )
    )
    assert count == dc.DAILY_QUEST_COUNT
