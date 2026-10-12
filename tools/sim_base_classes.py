"""Базовые классы до подкласса (1-29 ур.): соло против мобов своего кольца.

Запуск:  python tools/sim_base_classes.py [--rounds N]

Те же движок и бестиарий, что в игре (tools/sim_balance.py), характеристики
по стартовому распределению класса + 3 очка за уровень (60% основной, 30%
живучесть, 10% воля), без снаряжения. Сравнение классов между собой при
равных условиях - реальные бои ещё зависят от вещей и рук игрока.

Сложности: равный - моб уровня игрока, +3 - моб на 3 уровня выше (в пределах
кольца), сюжет - именной враг (x1.3 характеристик, как сюжетный 📜).
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from tools.sim_balance import REGIONS, make_fighter, run_tick_fight  # noqa: E402
from game.world import encounters  # noqa: E402

LEVELS = (3, 6, 10, 14, 17, 21, 25, 29)
CLASSES = ("warrior", "rogue", "mage")


def ring_dist(level: int) -> int:
    return 27 if level <= 15 else 19  # середина I и II кольца


def fight(cls: str, level: int, mode: str, rng: random.Random, i: int):
    player = make_fighter(1, 0, None, level, "dd", {}, base_class=cls)
    region = REGIONS[i % len(REGIONS)]
    dist = ring_dist(level)
    zone_max = 15 if level <= 15 else 30
    if mode == "+3":
        mob = encounters.spawn_mob(2, region, min(level + 3, zone_max), dist, rng).combatant
    elif mode == "сюжет":
        mob = encounters.spawn_named_enemy(2, "Сюжетный", "", level, 1.3).combatant
    else:
        mob = encounters.spawn_mob(2, region, level, dist, rng).combatant
    return run_tick_fight([player], [mob], rng)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=300)
    parser.add_argument("--seed", type=int, default=20261012)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    for mode in ("равный", "+3", "сюжет"):
        print(f"\n=== {mode}: побед / ходов / осталось HP ===")
        print("ур. " + "".join(f"{c:>24}" for c in CLASSES))
        for level in LEVELS:
            cells = []
            for cls in CLASSES:
                res = [fight(cls, level, mode, rng, i) for i in range(args.rounds)]
                win = sum(r.won for r in res) / len(res)
                turns = statistics.fmean(r.turns for r in res)
                hp = statistics.fmean(r.hp_left_share for r in res)
                cells.append(f"{win:7.0%} {turns:6.1f} {hp:8.0%}")
            print(f"{level:3} " + "".join(f"{c:>24}" for c in cells))


if __name__ == "__main__":
    main()
