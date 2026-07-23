"""Пресеты микробаффов: валидация, три уровня стоимости респека."""

import pytest

from game.combat import balance_config as bc
from game.content_loader import load_content
from services.preset_service import (
    PresetValidationError,
    save_preset,
    switch_active_preset,
    validate_preset,
)
from services.respec_service import full_class_reset
from services.wallet_service import NotEnoughCurrency, get_wallet
from models import BaseClass, CharacterStats, CharacterUnlockedBuff
from sqlalchemy import select

CATALOG = load_content().buffs

OK_SET = ["guardian_heavy_hand", "guardian_bulwark", "guardian_command"]


async def _unlock(db_session, character, *buff_ids: str) -> None:
    """Прямая разблокировка баффов в тестовой БД (в обход прохождения испытания)."""
    for buff_id in buff_ids:
        db_session.add(CharacterUnlockedBuff(character_id=character.id, buff_id=buff_id))
    await db_session.flush()


def test_valid_preset_passes() -> None:
    validate_preset(OK_SET, "guardian", CATALOG)


def test_too_few_buffs() -> None:
    with pytest.raises(PresetValidationError):
        validate_preset(OK_SET[:2], "guardian", CATALOG)


def test_too_many_buffs() -> None:
    six = [b for b in CATALOG][:6]
    with pytest.raises(PresetValidationError):
        validate_preset(six, "guardian", CATALOG)


def test_mono_damage_preset_rejected() -> None:
    """Нельзя собрать чистый моно-урон без обороны/утилити."""
    damage_only = ["guardian_heavy_hand", "guardian_reflection", "guardian_retribution"]
    with pytest.raises(PresetValidationError):
        validate_preset(damage_only, "guardian", CATALOG)


def test_defense_or_utility_satisfies_rule() -> None:
    with_utility = ["guardian_heavy_hand", "guardian_reflection", "guardian_command"]
    validate_preset(with_utility, "guardian", CATALOG)  # не бросает


def test_unknown_and_foreign_buffs_rejected() -> None:
    with pytest.raises(PresetValidationError):
        validate_preset(["nope", *OK_SET[:2]], "guardian", CATALOG)
    with pytest.raises(PresetValidationError):
        validate_preset(OK_SET, "elementalist", CATALOG)  # чужой пул


def test_duplicates_rejected() -> None:
    with pytest.raises(PresetValidationError):
        validate_preset(["guardian_bulwark"] * 3, "guardian", CATALOG)


async def test_save_preset_charges_farm(db_session, make_character) -> None:
    character = await make_character(farm=bc.PRESET_CHANGE_COST_FARM + 100, subclass="guardian")
    await _unlock(db_session, character, *OK_SET)
    preset = await save_preset(db_session, character, "Танк", OK_SET, CATALOG)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.farm_currency == 100  # уровень 2 — платно
    assert preset.buff_ids == OK_SET


async def test_save_preset_without_gold_fails(db_session, make_character) -> None:
    character = await make_character(farm=0, subclass="guardian")
    await _unlock(db_session, character, *OK_SET)
    with pytest.raises(NotEnoughCurrency):
        await save_preset(db_session, character, "Танк", OK_SET, CATALOG)


async def test_save_preset_rejects_locked_buff(db_session, make_character) -> None:
    """Патч 12: бафф подкласса нельзя вложить в пресет, пока испытание не пройдено."""
    character = await make_character(farm=bc.PRESET_CHANGE_COST_FARM + 100, subclass="guardian")
    with pytest.raises(PresetValidationError):
        await save_preset(db_session, character, "Танк", OK_SET, CATALOG)


async def test_switch_preset_is_free(db_session, make_character) -> None:
    character = await make_character(
        farm=bc.PRESET_CHANGE_COST_FARM * 2, subclass="guardian"
    )
    second_set = ["guardian_heavy_hand", "guardian_reflection", "guardian_provoker_mark"]
    await _unlock(db_session, character, *set(OK_SET) | set(second_set))
    p1 = await save_preset(db_session, character, "Танк", OK_SET, CATALOG)
    p2 = await save_preset(db_session, character, "ДД", second_set, CATALOG)
    wallet_before = (await get_wallet(db_session, character.id)).farm_currency

    await switch_active_preset(db_session, character.id, p2.id)  # уровень 1 — бесплатно
    assert (await get_wallet(db_session, character.id)).farm_currency == wallet_before
    assert p2.is_active and not p1.is_active

    await switch_active_preset(db_session, character.id, p1.id)
    assert p1.is_active and not p2.is_active


async def test_full_class_reset(db_session, make_character) -> None:
    character = await make_character(
        level=10, farm=0, donate=bc.CLASS_RESET_COST_DONATE, subclass="guardian"
    )
    stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    stats.strength = 42

    await full_class_reset(db_session, character, BaseClass.MAGE)  # уровень 3 — донат
    assert character.base_class == BaseClass.MAGE
    assert character.subclass is None
    # статы — к стартовому распределению НОВОГО класса (маг: 10/10/25/15/25)
    assert stats.strength == bc.STARTING_STATS["mage"]["STR"]
    assert stats.intellect == bc.STARTING_STATS["mage"]["INT"]
    assert stats.unspent_points == bc.STAT_POINTS_PER_LEVEL * 9
    wallet = await get_wallet(db_session, character.id)
    assert wallet.donate_currency == 0
