"""Симуляция «Жерновов Паломников» ботами - обоз и Мельник рядом с

Калибровка 2026-10-19 (40 заходов, боты без экипировки): полная группа -
Архивариус 13%, Мельник ~20%, обоз ~90%; втроём боссы 0%.
Архивариусом на тех же ботах (как tools/sim_raid_field.py сравнивает с
театром).

Запуск:  python tools/sim_raid_mill.py [--rounds N]

Боты разумные: носильщик несёт в свою очередь, помеченный «Замри» защищается,
двое ближайших бьют цепь, каравай берёт самый раненый. Без экипировки и
зелий - нижняя граница, живые сильнее.
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
from game.combat import raid_archive, raid_mill
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction

PARTY = ["guardian", "dark_mystic", "elementalist", "shadow_blade", "blood_knight"]
LEVEL = 60
MAX_TICKS = 200


def _party(size: int) -> list:
    subs = ["blood_knight"] if size == 1 else PARTY[:size]
    return [make_fighter(i + 1, 0, sub, LEVEL, REGISTRY[sub].natural_role.value) for i, sub in enumerate(subs)]


def _fight(players, stage, rng) -> dict:
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for p in players:
        p.current_hp, p.effects, p.cooldowns = p.max_hp, [], {}
        session.add(p)
    stage.setup(session)
    frozen: list[int] = []
    for tick in range(1, MAX_TICKS + 1):
        session.tick_number = tick
        actions = {}
        cargo = isinstance(stage, raid_mill.CargoStage)
        miller = isinstance(stage, raid_mill.MillerStage)
        if miller and stage.bread_open:
            hurt = min((p for p in players if p.alive), key=lambda p: p.current_hp / p.max_hp, default=None)
            if hurt is not None and hurt.current_hp < hurt.max_hp * 0.6:
                stage.take_bread(session, hurt.id)
        chain_hitters = 0
        for p in players:
            if not p.alive or p.id in frozen:
                continue
            if cargo and stage.can_carry(session, p.id):
                stage.claim()
                actions[p.id] = DeclaredAction(type=ActionType.SKIP, payload={"carry": True})
                continue
            if miller and stage.hold_id == p.id:
                actions[p.id] = DeclaredAction(type=ActionType.DEFEND)
                continue
            target = pick_target(p, session)
            if miller and stage.chain_id is not None and chain_hitters < 2:
                target = session.combatants[stage.chain_id]
                chain_hitters += 1
            elif cargo or miller:
                boss_ids = stage.reward_ids if miller else set(stage.pilgrim_ids)
                alive = [session.combatants[i] for i in boss_ids if session.combatants[i].alive]
                target = alive[0] if alive else target
            if target is None:
                continue
            action = choose_action(p, session, target)
            if action.type in (ActionType.ATTACK, ActionType.SKILL) and action.target_id is None:
                action = action.model_copy(update={"target_id": target.id})
            elif action.type == ActionType.ATTACK:
                action = action.model_copy(update={"target_id": target.id})
            actions[p.id] = action
        result = resolve_tick(session, actions, rng)
        out = stage.after_tick(session, result, rng)
        frozen = out.frozen
        if not any(p.alive for p in players):
            return {"won": False, "ticks": tick}
        if out.cleared or (result.finished and result.winner_side == 0):
            return {"won": True, "ticks": tick}
    return {"won": False, "ticks": MAX_TICKS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()
    rng = random.Random(11)
    stages = {
        "Архивариус": lambda size, players: raid_archive.ArchiveStage(start_id=20_600_000),
        "Обоз": lambda size, players: raid_mill.CargoStage(
            20_700_000, size, raid_mill.carry_order([p.subclass_id for p in players])),
        "Мельник": lambda size, players: raid_mill.MillerStage(20_800_000),
    }
    for name, build in stages.items():
        cells = []
        for size in (5, 3, 1):
            runs = []
            for _ in range(args.rounds):
                players = _party(size)
                runs.append(_fight(players, build(size, players), rng))
            won = sum(r["won"] for r in runs)
            ticks = statistics.fmean(r["ticks"] for r in runs if r["won"]) if won else 0
            cells.append(f"{size}: {100 * won // len(runs):3d}% ({ticks:4.0f} х.)")
        print(f"{name:12} " + "  ".join(cells))


if __name__ == "__main__":
    main()
