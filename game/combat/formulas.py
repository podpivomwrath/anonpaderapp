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


def dodge_chance(agi: int) -> float:
    """Шанс полностью избежать урона от обычной атаки (патч 34, ч.1). Потолок
    ТОЛЬКО от стата (DODGE_STAT_CAP) — внешние источники складываются поверх
    отдельно, см. game/combat/skills.py::compute_hit."""
    return min(bc.DODGE_PER_AGI * agi, bc.DODGE_STAT_CAP)


def ability_dodge_chance(agi: int) -> float:
    """Шанс уклониться от способности — доля (ABILITY_DODGE_RATIO) от уворота
    против обычных атак."""
    return dodge_chance(agi) * bc.ABILITY_DODGE_RATIO


def level_diff_modifiers(mob_level: int, player_level: int) -> tuple[float, float]:
    """Патч 26: моб выше уровнем бьёт сильнее и получает меньше урона.
    Возвращает (mob_damage_mult, mob_taken_mult); (1.0, 1.0), если моб не выше."""
    diff = mob_level - player_level
    if diff <= 0:
        return 1.0, 1.0
    mob_damage_mult = min(1 + bc.LVL_DIFF_DMG_BONUS * diff, bc.LVL_DIFF_DMG_CAP)
    mob_taken_mult = max(1 - bc.LVL_DIFF_DEF_BONUS * diff, bc.LVL_DIFF_DEF_FLOOR)
    return mob_damage_mult, mob_taken_mult


def mob_ring_multiplier(zone_min: int, zone_max: int) -> float:
    """Патч 26: множитель статов моба по глубине кольца — ключ MOB_RING_MULTIPLIERS
    сопоставляется с диапазоном зоны (game.world.world_config.ZONE_TABLE)."""
    return bc.MOB_RING_MULTIPLIERS.get((zone_min, zone_max), 1.0)


def mob_ring_damage_multiplier(zone_min: int, zone_max: int) -> float:
    """Патч 28: на урон кольцо действует вполовину слабее, чем на HP — иначе
    глубокие зоны становятся не только «мясистее», но и мгновенно смертельными."""
    full = mob_ring_multiplier(zone_min, zone_max)
    return 1 + (full - 1) * 0.5


def respawn_time_minutes(level: int) -> float:
    """1 мин на 1 ур. → RESPAWN_MAX_MINUTES на MAX_LEVEL, линейно."""
    span = bc.RESPAWN_MAX_MINUTES - bc.RESPAWN_MIN_MINUTES
    return bc.RESPAWN_MIN_MINUTES + span / (bc.MAX_LEVEL - 1) * (level - 1)
