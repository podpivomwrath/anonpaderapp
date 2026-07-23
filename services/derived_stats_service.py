"""Производные характеристики персонажа — ЕДИНЫЙ источник для бота и мини-аппа.

Использует те же formulas.py/balance_config.py, что и боевой резолвер, чтобы
предпросмотр в мини-аппе не мог разойтись с реальным боем.
"""

from dataclasses import dataclass

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


def compute(character: Character, stats: CharacterStats) -> DerivedStats:
    tier = formulas.tier_for_level(character.level)
    tier_mult = formulas.tier_multiplier(tier)

    primary_stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    primary_value = {
        "str": stats.strength,
        "agi": stats.agility,
        "int": stats.intellect,
    }[primary_stat]
    k_dmg = formulas.k_dmg_for(primary_stat)

    return DerivedStats(
        max_hp=round(formulas.hp(character.level, stats.vitality, tier_mult)),
        damage=round(formulas.damage(tier_mult, primary_value, k_dmg), 1),
        crit_chance=formulas.crit_chance(stats.agility),
        mitigation=formulas.mitigation(stats.vitality),
        control_resist=formulas.control_resist(stats.will),
        support_power=formulas.support_power(stats.will),
    )
