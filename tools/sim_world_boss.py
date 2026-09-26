"""Сколько урона наносит один заход к мировому боссу (патч 104).

Запуск:  python tools/sim_world_boss.py [--rounds N]

Игрок уровня босса (без экипировки, как в tools/sim_balance.py) 10 ходов
бьёт босса, который не отвечает. Здоровье босса в конфиге = средний урон
захода x REAL_DAMAGE_FACTOR x ATTEMPTS_TO_KILL (game/economy/world_boss_config.py).

До 30 уровня подклассов нет - там считаются базовые классы.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim_balance import choose_action, make_fighter

from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.session import CombatMode, CombatSessionState
from game.economy import world_boss_config as wbc
from game.world import world_boss

BIG_HP = 10**9


def one_attempt(fighter_id: str, ring: int, rng: random.Random) -> int:
    level = world_boss.boss_level(ring)
    if level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL:
        role = REGISTRY[fighter_id].natural_role.value
        player = make_fighter(1, 0, fighter_id, level, role)
    else:
        player = make_fighter(1, 0, None, level, "dd", base_class=fighter_id)
    boss_def = next(iter(world_boss.boss_defs().values()))
    boss = world_boss.build_combatant(2, boss_def, ring, BIG_HP, BIG_HP)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    session.add(player)
    session.add(boss)
    for _ in range(wbc.ATTEMPT_TURNS):
        session.tick_number += 1
        resolve_tick(session, {1: choose_action(player, session, boss)}, rng)
    return BIG_HP - boss.current_hp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()
    rng = random.Random(104)
    for ring in sorted(wbc.RINGS):
        level = world_boss.boss_level(ring)
        fighters = (
            sorted(REGISTRY) if level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL
            else ["warrior", "rogue", "mage"]
        )
        per_fighter = {
            f: statistics.fmean(one_attempt(f, ring, rng) for _ in range(args.rounds))
            for f in fighters
        }
        avg = statistics.fmean(per_fighter.values())
        lo, hi = min(per_fighter, key=per_fighter.get), max(per_fighter, key=per_fighter.get)
        print(
            f"кольцо {wbc.RING_NAMES[ring]:>3} (ур.{level}): заход в среднем {avg:8.0f}"
            f" | меньше всех {lo} {per_fighter[lo]:.0f}, больше всех {hi} {per_fighter[hi]:.0f}"
            f" | живой заход ~{avg * wbc.REAL_DAMAGE_FACTOR:.0f}"
            f" | здоровье на {wbc.ATTEMPTS_TO_KILL} заходов:"
            f" {round(avg * wbc.REAL_DAMAGE_FACTOR * wbc.ATTEMPTS_TO_KILL, -3):.0f}"
        )


if __name__ == "__main__":
    main()
