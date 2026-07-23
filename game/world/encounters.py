"""Спавн PvE-встреч стартового кольца.

Уровень моба клампится под игрока в диапазон зоны (world-patch-1):
  mob_level = clamp(player_level, zone_min, zone_max)
Мобы и флейвор — из content/mobs/starter_ring.json (все порождения раскола).
"""

import random
from dataclasses import dataclass

from game.combat.session import CombatantState, Stats, build_combatant
from game.content_loader import StarterRingMob, load_starter_ring

_starter_ring: dict[str, list[StarterRingMob]] | None = None


def _region_mobs(region: str) -> list[StarterRingMob]:
    global _starter_ring
    if _starter_ring is None:
        _starter_ring = load_starter_ring()
    return _starter_ring[region]


def balanced_mob_stats(level: int) -> Stats:
    """«Средний сбалансированный» моб: пул очков поровну между статами
    (та же идея, что и balancedStats в историческом sim.js-прототипе)."""
    pool = 75 + 3 * level
    base = pool // 5
    remainder = pool - base * 5
    return Stats(
        strength=base,
        agility=base,
        intellect=base,
        vitality=base + remainder,  # остаток — в живучесть
        will=base,
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
    participant_id: int, region: str, player_level: int, rng: random.Random
) -> Encounter:
    """Урон моба завязан на STR-эквивалент (K_dmg=2), как у Воина/Мага.
    Возвращает участника боя + флейвор-текст для показа перед боем."""
    mob = rng.choice(_region_mobs(region))
    level = mob_level_for_player(player_level, mob)
    combatant = build_combatant(
        id=participant_id,
        side=1,
        kind="mob",
        name=mob.name,
        level=level,
        stats=balanced_mob_stats(level),
        primary_stat="str",
    )
    return Encounter(combatant=combatant, flavor=mob.flavor)
