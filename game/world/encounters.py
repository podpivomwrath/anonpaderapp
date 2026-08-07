"""Спавн PvE-встреч по кольцам карты (патч 15: все 5 колец, не только стартовое).

Уровень моба клампится под игрока в диапазон зоны (world-patch-1):
  mob_level = clamp(player_level, zone_min, zone_max)
Мобы и флейвор — из content/mobs/*.json (все порождения раскола).

Кольцо выбирается по ТЕКУЩЕМУ положению игрока (dist до Монолита), не по его
домашнему региону — регион влияет только на тематику мобов (кроме центра,
dist 0-2, где мобы общие для всех регионов, ключ "any")."""

import random
from dataclasses import dataclass

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import CombatantState, Stats, build_combatant
from game.content_loader import StarterRingMob, load_bestiary
from game.world import grid
from game.world import world_config as wc

_bestiary: dict[str, list[StarterRingMob]] | None = None


def _region_mobs(region: str) -> list[StarterRingMob]:
    global _bestiary
    if _bestiary is None:
        _bestiary = load_bestiary()
    return _bestiary.get(region, [])


def balanced_mob_stats(level: int, primary_stat: str = "str") -> Stats:
    """Специализированное распределение статов моба (патч 26): основной
    боевой стат (STR/AGI/INT по теме моба из бестиария) забирает львиную
    долю бюджета, VIT — живучесть, остальные три статы — по крохам
    (MOB_STAT_ALLOCATION). Раньше бюджет размазывался поровну — из-за этого
    моб вдвое выше уровнем не был опаснее игрока со специализированными
    статами (см. патч 26, диагноз)."""
    pool = 75 + 3 * level
    primary_val = round(pool * bc.MOB_STAT_ALLOCATION["primary"])
    vit_val = round(pool * bc.MOB_STAT_ALLOCATION["vit"])
    other_val = round(pool * bc.MOB_STAT_ALLOCATION["other"])
    by_key = {"str": other_val, "agi": other_val, "int": other_val, "wil": other_val}
    by_key[primary_stat] = primary_val
    return Stats(
        strength=by_key["str"],
        agility=by_key["agi"],
        intellect=by_key["int"],
        vitality=vit_val,
        will=by_key["wil"],
    )


def _scale_stats_split(stats: Stats, hp_mult: float, dmg_mult: float) -> Stats:
    """Патч 28: VIT (длина боя) и остальные статы (опасность/урон) масштабируются
    раздельными множителями — см. MOB_HP_MULTIPLIER/MOB_DAMAGE_MULTIPLIER."""
    return Stats(
        strength=round(stats.strength * dmg_mult),
        agility=round(stats.agility * dmg_mult),
        intellect=round(stats.intellect * dmg_mult),
        vitality=round(stats.vitality * hp_mult),
        will=round(stats.will * dmg_mult),
    )


def mob_level_for_player(player_level: int, mob: StarterRingMob) -> int:
    """clamp(player_level, zone_min, zone_max) — моб равен игроку внутри зоны,
    но не ниже нижней границы (зашёл рано) и не выше потолка зоны."""
    return max(mob.zone_min, min(player_level, mob.zone_max))


@dataclass
class Encounter:
    combatant: CombatantState
    flavor: str


def spawn_mob(
    participant_id: int, region: str, player_level: int, dist: int, rng: random.Random
) -> Encounter:
    """dist (патч 15) — расстояние Чебышёва до Монолита ТЕКУЩЕЙ клетки игрока:
    определяет, какое кольцо бестиария используется (не домашний регион).
    Урон моба завязан на STR-эквивалент (K_dmg=2), как у Воина/Мага.
    Возвращает участника боя + флейвор-текст для показа перед боем."""
    zone = grid.zone_level_range(dist)
    center_lo, center_hi, _ = wc.ZONE_TABLE[-1]
    pool_region = "any" if center_lo <= dist <= center_hi else region
    candidates = [m for m in _region_mobs(pool_region) if (m.zone_min, m.zone_max) == zone]
    mob = rng.choice(candidates)
    level = mob_level_for_player(player_level, mob)
    # Патч 28: раздельные множители — HP (длина боя) получает кольцо целиком,
    # урон (опасность) — вполовину слабее (см. balance_config.py).
    hp_mult = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone)
    dmg_mult = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone)
    stats = _scale_stats_split(balanced_mob_stats(level, mob.primary_stat), hp_mult, dmg_mult)
    combatant = build_combatant(
        id=participant_id,
        side=1,
        kind="mob",
        name=mob.name,
        level=level,
        stats=stats,
        primary_stat=mob.primary_stat,
    )
    return Encounter(combatant=combatant, flavor=mob.flavor)


def spawn_named_enemy(
    participant_id: int, name: str, flavor: str, level: int, stat_mult: float
) -> Encounter:
    """Именной сюжетный враг (патч 18) — та же balanced_mob_stats, что и у
    обычного моба, но с уникальным именем/флейвором и множителем к статам
    (НЕ босс — просто усилен, см. game/economy/story_config.py)."""
    base = balanced_mob_stats(level)
    scaled = Stats(
        strength=round(base.strength * stat_mult),
        agility=round(base.agility * stat_mult),
        intellect=round(base.intellect * stat_mult),
        vitality=round(base.vitality * stat_mult),
        will=round(base.will * stat_mult),
    )
    combatant = build_combatant(
        id=participant_id, side=1, kind="mob", name=name, level=level,
        stats=scaled, primary_stat="str",
    )
    return Encounter(combatant=combatant, flavor=flavor)
