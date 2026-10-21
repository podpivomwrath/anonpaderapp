"""Производные характеристики персонажа — ЕДИНЫЙ источник для бота и мини-аппа.

Использует те же formulas.py/balance_config.py, что и боевой резолвер, чтобы
предпросмотр в мини-аппе не мог разойтись с реальным боем.
"""

from dataclasses import dataclass

from game.classes.poisoner import poison_tick_damage_per_stack
from game.combat import balance_config as bc
from game.combat import formulas
from models import Character, CharacterStats


@dataclass(frozen=True)
class DerivedStats:
    max_hp: int
    damage: float
    crit_chance: float
    mitigation: float
    control_resist: float
    support_power: float
    dodge_chance: float
    ability_dodge_chance: float
    #: Урон ядом Отравителя за ход при полном числе стаков. Считается НЕ от
    #: урона атаки, а от Воли и Ловкости, поэтому по остальным статам его
    #: не видно вовсе - без этой строки игрок не может понять, что качать.
    poison_power: float


def compute(
    character: Character, stats: CharacterStats, gear_bonus: dict[str, int] | None = None
) -> DerivedStats:
    """gear_bonus (патч 11, блок 2) — сумма статов надетой экипировки
    (services.item_service.gear_bonus), прибавляется к собственным статам ДО
    расчёта формул. None/пусто — экипировка не учитывается (как раньше)."""
    bonus = gear_bonus or {}
    strength = stats.strength + bonus.get("str", 0)
    agility = stats.agility + bonus.get("agi", 0)
    intellect = stats.intellect + bonus.get("int", 0)
    vitality = stats.vitality + bonus.get("vit", 0)
    will = stats.will + bonus.get("wil", 0)

    tier = formulas.tier_for_level(character.level)
    tier_mult = formulas.tier_multiplier(tier)

    primary_stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    primary_value = {"str": strength, "agi": agility, "int": intellect}[primary_stat]
    k_dmg = formulas.k_dmg_for(primary_stat)

    return DerivedStats(
        max_hp=round(round(formulas.hp(character.level, vitality, tier_mult)
                           * formulas.class_hp_mult(character.base_class, character.subclass))
                     * _food_hp_mult(character)),
        damage=round(formulas.damage(tier_mult, primary_value, k_dmg), 1),
        crit_chance=min(formulas.crit_chance(agility)
                        + formulas.class_crit_bonus(character.base_class, character.subclass), 1.0),
        mitigation=formulas.mitigation(vitality),
        control_resist=formulas.control_resist(will),
        support_power=formulas.support_power(will),
        dodge_chance=formulas.dodge_chance(agility),
        ability_dodge_chance=formulas.ability_dodge_chance(agility),
        poison_power=round(
            poison_tick_damage_per_stack(will, agility) * bc.POISONER_MAX_STACKS, 1
        ),
    )


def _food_hp_mult(character) -> float:
    """Еда (2026-10-21): здоровье в карточке - с баффом, как в бою."""
    from services import cooking_service

    return cooking_service.hp_mult(character) if hasattr(character, "food_dish") else 1.0
