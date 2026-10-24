"""Производные характеристики персонажа — ЕДИНЫЙ источник для бота и мини-аппа.

Использует те же formulas.py/balance_config.py, что и боевой резолвер, чтобы
предпросмотр в мини-аппе не мог разойтись с реальным боем.
"""

from dataclasses import dataclass

from game.classes.poisoner import poison_tick_damage_per_stack
from game.combat import balance_config as bc
from game.combat import formulas, stat_model
from game.combat.session import Stats
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
    # Проценты и урон - той же моделью статов, что и бой (game/combat/stat_model).
    model = stat_model.ACTIVE
    s = Stats(strength=strength, agility=agility, intellect=intellect, vitality=vitality, will=will)

    return DerivedStats(
        max_hp=round(round(formulas.hp(character.level, vitality, tier_mult)
                           * formulas.class_hp_mult(character.base_class, character.subclass))
                     * _food_hp_mult(character)),
        damage=round(formulas.damage(
            tier_mult, model.primary_value(primary_value, character.level, True), k_dmg), 1),
        crit_chance=min(model.crit_chance(s) + stat_model.subclass_crit_bonus(character.subclass)
                        + formulas.class_crit_bonus(character.base_class, character.subclass), 1.0),
        mitigation=model.mitigation(s),
        control_resist=model.control_resist(will),
        support_power=model.support_power(s),
        dodge_chance=model.dodge(s, False) + stat_model.subclass_dodge_bonus(character.subclass),
        ability_dodge_chance=model.dodge(s, True) + stat_model.subclass_dodge_bonus(character.subclass),
        poison_power=round(
            poison_tick_damage_per_stack(will, agility) * bc.POISONER_MAX_STACKS, 1
        ),
    )


def _food_hp_mult(character) -> float:
    """Еда (2026-10-21): здоровье в карточке - с баффом, как в бою."""
    from services import cooking_service

    return cooking_service.hp_mult(character) if hasattr(character, "food_dish") else 1.0
