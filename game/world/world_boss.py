"""Мировые боссы (патч 104): чистая логика без БД и VK.

Где встаёт, какой силы, как собирается боец для движка и как пул награды
делится между участниками. Состояние мира (сам босс, его здоровье, вклады)
- в services/world_boss_service.py.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat import session as combat_session
from game.combat.session import CombatantState
from game.content_loader import WorldBossDef, load_world_bosses
from game.economy import fishing, mining
from game.economy import world_boss_config as wbc
from game.world import encounters, grid

_defs: dict[str, WorldBossDef] | None = None


def boss_defs() -> dict[str, WorldBossDef]:
    global _defs
    if _defs is None:
        _defs = {b.id: b for b in load_world_bosses()}
    return _defs


def boss_def(boss_id: str) -> WorldBossDef | None:
    return boss_defs().get(boss_id)


def boss_level(ring: int) -> int:
    return wbc.RINGS[ring][0]


def max_attacker_level(ring: int) -> int:
    return boss_level(ring) + wbc.MAX_LEVEL_OVER_RING


def can_attack(player_level: int, ring: int) -> bool:
    return player_level <= max_attacker_level(ring)


def ring_of_level(level: int) -> int | None:
    """Самое внешнее кольцо, куда игрок этого уровня ещё допускается."""
    for ring in sorted(wbc.RINGS):
        if can_attack(level, ring):
            return ring
    return None


def pick_ring(rng: random.Random, players_by_ring: dict[int, int]) -> int:
    """Кольцо чаще там, где сейчас играют: вес = 1 + игроков, которым этот
    босс по уровню. Единица - чтобы и пустое кольцо иногда получало босса."""
    rings = sorted(wbc.RINGS)
    weights = [1 + players_by_ring.get(r, 0) for r in rings]
    return rng.choices(rings, weights=weights)[0]


def _cell_is_free(x: int, y: int) -> bool:
    """Не город, не озеро и не рудник: у тех клеток свои кнопки, и босс
    среди них потерялся бы."""
    return (
        grid.in_bounds(x, y)
        and grid.city_region_at(x, y) is None
        and fishing.lake_at(x, y) is None
        and mining.mine_at(x, y) is None
    )


def pick_cell(ring: int, rng: random.Random) -> tuple[int, int]:
    """Случайная клетка кольца: сначала расстояние до Монолита, потом точка на
    этом «квадрате» (расстояние Чебышёва)."""
    lo, hi = wbc.RINGS[ring][1]
    while True:
        dist = rng.randint(lo, hi)
        side = rng.randint(-dist, dist)
        x, y = rng.choice([(side, dist), (side, -dist), (dist, side), (-dist, side)])
        if _cell_is_free(x, y):
            return x, y


def _stands_still(mob: CombatantState, session, rng) -> list:
    """Ход босса: ничего. Мировой босс не бьёт в ответ - заход это гонка
    урона, а не бой на выживание (решение владельца игры)."""
    return []


def build_combatant(
    participant_id: int, boss: WorldBossDef, ring: int, hp: int, max_hp: int,
) -> CombatantState:
    """Боец для движка. Статы - как у обычного моба уровня босса в этом
    кольце (от них зависит, насколько он держит удар), здоровье - общее."""
    level = boss_level(ring)
    zone = grid.zone_level_range(wbc.RINGS[ring][1][0])
    hp_mult = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone)
    dmg_mult = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone)
    stats = encounters._scale_stats_split(encounters.balanced_mob_stats(level), hp_mult, dmg_mult)
    combatant = combat_session.build_combatant(
        id=participant_id, side=1, kind="mob", name=boss.name, level=level,
        stats=stats, primary_stat="str",
    )
    combatant.max_hp = max_hp
    combatant.current_hp = hp
    combatant.scripted_hit = _stands_still
    return combatant


# --- Пул награды --------------------------------------------------------------


@dataclass
class PoolShare:
    """Что досталось одному участнику."""

    xp: int = 0
    #: Редкости выпавших вещей - сами вещи генерирует сервис под класс игрока.
    items: list[str] = field(default_factory=list)
    trophies: dict[str, int] = field(default_factory=dict)
    elixirs: dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.xp or self.items or self.trophies or self.elixirs)


def _lots(amount: int, share: float) -> int:
    return round(amount * share)


def _roll_rarity(rng: random.Random) -> str:
    rarities = list(wbc.ITEM_RARITY_CHANCES)
    return rng.choices(rarities, weights=[wbc.ITEM_RARITY_CHANCES[r] for r in rarities])[0]


def split_pool(
    ring: int, damage_by: dict[int, int], share: float, xp_pool: int, rng: random.Random,
) -> dict[int, PoolShare]:
    """Делит пул кольца между участниками.

    share - какая часть пула разыгрывается: 1.0 за убийство, доля снятого
    здоровья - если босс ушёл живым. Опыт делится пропорционально урону;
    каждая вещь, трофей и склянка разыгрываются отдельно, шанс участника -
    его доля урона. Кто бил больше, чаще забирает, но и у слабого есть шанс.
    """
    damage_by = {cid: dmg for cid, dmg in damage_by.items() if dmg > 0}
    if not damage_by:
        return {}
    total = sum(damage_by.values())
    ids = list(damage_by)
    weights = [damage_by[cid] for cid in ids]
    result = {cid: PoolShare() for cid in ids}

    xp_total = round(xp_pool * share)
    for cid in ids:
        result[cid].xp = xp_total * damage_by[cid] // total

    def winner() -> PoolShare:
        return result[rng.choices(ids, weights=weights)[0]]

    for _ in range(_lots(wbc.ITEMS_BY_RING[ring], share)):
        winner().items.append(_roll_rarity(rng))
    for trophy_id, amount in wbc.TROPHIES_BY_RING[ring].items():
        for _ in range(_lots(amount, share)):
            got = winner().trophies
            got[trophy_id] = got.get(trophy_id, 0) + 1
    heal_id, heal_amount = wbc.HEALS_BY_RING[ring]
    for _ in range(_lots(heal_amount, share)):
        got = winner().elixirs
        got[heal_id] = got.get(heal_id, 0) + 1
    for _ in range(_lots(wbc.COMBAT_ELIXIRS_BY_RING[ring], share)):
        elixir_id = rng.choice(wbc.COMBAT_ELIXIRS)
        got = winner().elixirs
        got[elixir_id] = got.get(elixir_id, 0) + 1
    return result
