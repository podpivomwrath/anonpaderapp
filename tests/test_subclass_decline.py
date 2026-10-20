"""Отказ от подкласса у Хранителя Списков (2026-10-20): базовый класс навсегда,
пресеты из пула "<класс>_path", открытого сразу."""

import random

import pytest

from game.combat import balance_config as bc
from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.resolver import resolve_tick
from game.content_loader import load_content
from models import BaseClass
from services import power_service, preset_service, subclass_service
from services.preset_service import PresetValidationError
from services.respec_service import full_class_reset
from tests.conftest import NoCritRng, combatant
from tests.test_base_skills import make_session, skill

CATALOG = load_content().buffs
WARRIOR_SET = ["warrior_path_hardened", "warrior_path_heavy_swing", "warrior_path_deep_cut"]


def test_every_base_class_has_a_full_pool() -> None:
    for cls in ("warrior", "rogue", "mage"):
        pool = [b for b in CATALOG.values() if b.subclass == f"{cls}_path"]
        assert len(pool) >= bc.PRESET_MAX_BUFFS + 3, cls
        assert all(b.implemented for b in pool)


async def test_decline_opens_base_pool_without_trials(db_session, make_character) -> None:
    character = await make_character(level=30, farm=10_000)
    assert subclass_service.buff_pool(character) is None
    subclass_service.decline(character)
    assert not subclass_service.can_offer(character)
    assert subclass_service.path_chosen(character)
    assert subclass_service.buff_pool(character) == "warrior_path"

    preset = await preset_service.save_preset(db_session, character, "Путь", WARRIOR_SET, CATALOG)
    await preset_service.switch_active_preset(db_session, character, preset.id)
    mods = await preset_service.resolve_active_modifiers(db_session, character)
    assert mods["incoming_damage_reduction"] == pytest.approx(CATALOG["warrior_path_hardened"].stat_modifiers["incoming_damage_reduction"])
    power = await power_service.power_of(db_session, character)
    assert power.subclass_bonus > 0 and power.buffs == 3


def test_foreign_path_buffs_rejected() -> None:
    with pytest.raises(PresetValidationError):
        preset_service.validate_preset(WARRIOR_SET, "rogue_path", CATALOG, set())
    with pytest.raises(PresetValidationError):
        preset_service.validate_preset(WARRIOR_SET, "guardian", CATALOG, set())
    preset_service.validate_preset(WARRIOR_SET, "warrior_path", CATALOG, set())


async def test_only_full_class_change_clears_decline(db_session, make_character) -> None:
    character = await make_character(level=30)
    subclass_service.decline(character)
    await full_class_reset(db_session, character, BaseClass.MAGE)
    assert not subclass_service.declined(character)
    assert subclass_service.can_offer(character)
    assert not character.subclass_free_repick  # за путь не платили - повтор не бесплатный


def test_path_skill_buffs_change_damage_and_cooldown() -> None:
    cleave = BASE_SKILL_DEFS["warrior_cleave"]
    stagger = BASE_SKILL_DEFS["warrior_stagger"]

    def hit(mods: dict) -> int:
        a = combatant(1, side=0, strength=100)
        a.primary_stat = "str"
        a.buff_modifiers = mods
        b = combatant(2, side=1, vitality=500, agility=0)
        result = resolve_tick(make_session(a, b), {1: skill("warrior_cleave", 2)}, NoCritRng())
        return sum(h.amount for h in result.hits if h.target_id == 2)

    plain = hit({})
    boosted = hit({"skill_bonus:warrior_cleave": 0.4})
    assert boosted / plain == pytest.approx((cleave.multiplier + 0.4) / cleave.multiplier, rel=0.05)

    a = combatant(1, side=0)
    a.buff_modifiers = {"skill_cd:warrior_stagger": 1}
    b = combatant(2, side=1, vitality=500)
    resolve_tick(make_session(a, b), {1: skill("warrior_stagger", 2)}, random.Random(1))
    assert a.cooldowns["warrior_stagger"] <= stagger.cd - 1
