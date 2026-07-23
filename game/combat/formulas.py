"""Формулы боевой системы — v2 (текущая калибруемая версия).

Все константы — в balance_config.py. Имена функций соответствуют
дизайн-документу; sim.js в корне — исторический прототип v1.
"""

from game.combat import balance_config as bc


def tier_for_level(level: int) -> str:
    if level <= 15:
        return "grey"
    if level <= 30:
        return "white"
    if level <= 45:
        return "green"
    if level <= 60:
        return "blue"
    if level <= 80:
        return "epic"
    return "legendary"


def tier_multiplier(tier: str) -> float:
    return bc.TIER_MULTIPLIERS[tier]


def hp(level: int, vit: int, tier_mult: float) -> float:
    return bc.HP_BASE + bc.HP_PER_LEVEL * level + bc.HP_PER_VIT * vit + bc.HP_PER_TIER * tier_mult


def weapon_base(tier_mult: float) -> float:
    return bc.WEAPON_BASE_PER_TIER * tier_mult


def k_dmg_for(primary_stat: str) -> float:
    """primary_stat: "str" | "agi" | "int"."""
    return bc.K_DMG[primary_stat]


def damage(tier_mult: float, primary_stat: int, k_dmg: float) -> float:
    return weapon_base(tier_mult) + k_dmg * primary_stat


def crit_chance(agi: int) -> float:
    return min(bc.CRIT_PER_AGI * agi, bc.CRIT_CAP)


def mitigation(vit: int) -> float:
    return min(bc.MITIGATION_PER_VIT * vit, bc.MITIGATION_CAP)


def control_resist(wil: int) -> float:
    return min(bc.CONTROL_RESIST_PER_WIL * wil, bc.CONTROL_RESIST_CAP)


def support_power(wil: int) -> float:
    return bc.SUPPORT_POWER_PER_WIL * wil  # без потолка


def respawn_time_minutes(level: int) -> float:
    """1 мин на 1 ур. → RESPAWN_MAX_MINUTES на MAX_LEVEL, линейно."""
    span = bc.RESPAWN_MAX_MINUTES - bc.RESPAWN_MIN_MINUTES
    return bc.RESPAWN_MIN_MINUTES + span / (bc.MAX_LEVEL - 1) * (level - 1)
