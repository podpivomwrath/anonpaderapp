"""Симуляция боя с Безымянным («Тропа Безымянного», этап 3) ботами - рядом
с Мельником на тех же ботах (tools/sim_raid_mill.py).

Запуск:  python tools/sim_raid_trail.py [--rounds N]

Калибровка 2026-10-20 (40 заходов, боты без экипировки): впятером ~52%
(отпечатки раз в 3 хода, жжёт с 4-го, 45 000 HP); втроём и соло 0%, как у
остальных рейдовых боссов. Мельник при правильной игре с цепью - ~50%.

Боты разумные: видят отпечатки - уходят на безопасную соседнюю клетку,
стоят на месте BURN_AFTER-1 ходов - шагают, рядом безымянный союзник -
окликают его. Без экипировки и зелий - нижняя граница, живые сильнее.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim_balance import choose_action, pick_target
from sim_raid_mill import MAX_TICKS, _party

from game.combat import raid_mill
from game.combat import raid_trail as trail
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction
from game.economy import raid_trail_config as tc


def _safe_step(stage: trail.NamelessStage, cid: int, rng: random.Random) -> int | None:
    here = stage.pos[cid]
    bad = stage.danger(cid)
    options = [c for c in range(trail.CELLS) if trail.adjacent(here, c) and c not in bad]
    return rng.choice(options) if options else None


def _step_choice(stage, cid, rng) -> int | None:
    here = stage.pos.get(cid)
    if here is None:
        return None
    if here in stage.danger(cid):
        return _safe_step(stage, cid, rng)
    for other in stage.nameless:
        if other != cid and trail.adjacent(here, stage.pos.get(other, -9)) \
                and stage.pos[other] not in stage.danger(cid):
            return stage.pos[other]
    if stage.still.get(cid, 0) >= tc.BURN_AFTER - 1:
        return _safe_step(stage, cid, rng)
    return None


def _fight(players, stage, rng) -> dict:
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for p in players:
        p.current_hp, p.effects, p.cooldowns = p.max_hp, [], {}
        session.add(p)
    stage.setup(session)
    boss = session.combatants[stage.boss_id]
    for tick in range(1, MAX_TICKS + 1):
        session.tick_number = tick
        actions = {}
        for p in players:
            if not p.alive:
                continue
            step = _step_choice(stage, p.id, rng)
            if step is not None:
                actions[p.id] = DeclaredAction(type=ActionType.SKIP, payload={"step": step})
                continue
            target = boss if boss.alive else pick_target(p, session)
            action = choose_action(p, session, target)
            if action.type in (ActionType.ATTACK, ActionType.SKILL) and action.target_id is None:
                action = action.model_copy(update={"target_id": target.id})
            elif action.type == ActionType.ATTACK:
                action = action.model_copy(update={"target_id": target.id})
            actions[p.id] = action
        result = resolve_tick(session, actions, rng)
        stage.after_tick(session, result, rng)
        if not any(p.alive for p in players):
            return {"won": False, "ticks": tick}
        if not boss.alive or (result.finished and result.winner_side == 0):
            return {"won": True, "ticks": tick}
    return {"won": False, "ticks": MAX_TICKS}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=40)
    args = parser.parse_args()
    stages = {
        "Мельник": lambda: raid_mill.MillerStage(20_800_000),
        "Безымянный": lambda: trail.NamelessStage(20_900_000),
    }
    from sim_raid_mill import _fight as mill_fight

    for name, build in stages.items():
        cells = []
        for size in (5, 3, 1):
            rng = random.Random(11)
            fight = _fight if name == "Безымянный" else mill_fight
            runs = [fight(_party(size), build(), rng) for _ in range(args.rounds)]
            won = sum(r["won"] for r in runs)
            ticks = statistics.fmean(r["ticks"] for r in runs if r["won"]) if won else 0
            cells.append(f"{size}: {100 * won // len(runs):3d}% ({ticks:4.0f} х.)")
        print(f"{name:12} " + "  ".join(cells))


if __name__ == "__main__":
    main()
