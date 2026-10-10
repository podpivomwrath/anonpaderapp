"""Симуляция разломов ботами.

Запуск:  python tools/sim_rift.py [--rounds N] [--levels 15,30,45,60]

Для каждого типа и уровня - группа по потолку разлома, неполная группа и
одиночка. Игроки без экипировки и зелий (как tools/sim_raid_field.py):
живые с экипировкой заметно сильнее, поэтому здесь - нижняя граница.
Цель (решение владельца): полная группа проходит, одиночка - на грани
невозможного.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sim_balance import choose_action, make_fighter, pick_target

from game.classes.base import REGISTRY
from game.combat import rift
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState
from game.economy import rift_config as rc

PARTY = ["guardian", "dark_mystic", "elementalist", "shadow_blade", "blood_knight"]
SOLO = "blood_knight"
MAX_TICKS = 200


def _ring(level: int) -> int:
    return next(r for r, (lo, hi) in rc.BANDS.items() if lo <= level <= hi)


def _party(size: int, level: int) -> list:
    subs = [SOLO] if size == 1 else (PARTY * 2)[:size]
    return [make_fighter(i + 1, 0, sub, level, REGISTRY[sub].natural_role.value) for i, sub in enumerate(subs)]


def run(kind: str, size: int, level: int, rng: random.Random) -> dict:
    players = _party(size, level)
    out = {"won": False, "stage": 1, "ticks": 0}
    for stage_no in range(1, rift.stage_count(kind) + 1):
        out["stage"] = stage_no
        for p in players:
            p.current_hp, p.effects, p.cooldowns = p.max_hp, [], {}
        session = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
        for p in players:
            session.add(p)
        stage = rift.build_stage(kind, stage_no, 30_000_000 + stage_no * 100_000, level, _ring(level))
        stage.setup(session)
        frozen: list[int] = []
        cleared = False
        for _ in range(MAX_TICKS):
            session.tick_number += 1
            actions = {}
            for p in players:
                if not p.alive or p.id in frozen:
                    continue
                target = pick_target(p, session)
                if target is None:
                    continue
                action = choose_action(p, session, target)
                if action.type == ActionType.SKILL and action.target_id is None:
                    action = action.model_copy(update={"target_id": target.id})
                actions[p.id] = action
            result = resolve_tick(session, actions, rng)
            tick = stage.after_tick(session, result, rng)
            frozen = tick.frozen
            out["ticks"] += 1
            if not any(p.alive for p in players):
                return out
            if tick.cleared or (result.finished and result.winner_side == 0):
                cleared = True
                break
        if not cleared:
            return out
    out["won"] = True
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=40)
    parser.add_argument("--levels", default="15,30,45,60")
    args = parser.parse_args()
    rng = random.Random(11)
    for kind, rtype in rc.RIFT_TYPES.items():
        sizes = sorted({rtype.max_size, max(1, rtype.max_size - 2), 1}, reverse=True)
        for level in (int(v) for v in args.levels.split(",")):
            cells = []
            for size in sizes:
                runs = [run(kind, size, level, rng) for _ in range(args.rounds)]
                won = sum(r["won"] for r in runs)
                ticks = statistics.fmean(r["ticks"] for r in runs if r["won"]) if won else 0
                cells.append(f"{size}: {100 * won // len(runs):3d}% ({ticks:4.0f} х.)")
            print(f"{rtype.name:18} ур.{level:2}  " + "  ".join(cells))


if __name__ == "__main__":
    main()
