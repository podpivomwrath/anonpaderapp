"""Симуляция рейда «Безмогильное поле» ботами.

Запуск:  python tools/sim_raid_field.py [--rounds N] [--size 5]

Две тактики группы:
- «умная» читает поле: спасает схваченного, бьёт курган разными руками,
  отвечает на стойки так, как велит подсказка (обманку не распознаёт);
- «бездумная» всегда бьёт самого слабого противника лучшим ударом.

Игроки 60 уровня без экипировки (как в tools/sim_balance.py) - живые с
экипировкой сильнее, поэтому числа здесь - нижняя граница для группы.
Между этапами HP и откаты восстанавливаются, как в настоящем рейде.
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
from game.combat import raid_field as rf
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction

PARTY = ["guardian", "dark_mystic", "elementalist", "shadow_blade", "blood_knight"]
MAX_TICKS = 80


def _party(size: int) -> list:
    subs = (PARTY * 2)[:size]
    return [make_fighter(i + 1, 0, sub, 60, REGISTRY[sub].natural_role.value) for i, sub in enumerate(subs)]


def _fresh(players: list) -> None:
    for p in players:
        p.current_hp = p.max_hp
        p.effects = []
        p.cooldowns = {}


def _attack(actor, session, target) -> DeclaredAction:
    action = choose_action(actor, session, target)
    if action.type == ActionType.SKILL and action.target_id is None:
        action = action.model_copy(update={"target_id": target.id})
    return action


def _is_offensive_on(action: DeclaredAction, target_id: int) -> bool:
    return action.target_id == target_id and action.type in (ActionType.ATTACK, ActionType.SKILL) and not (
        action.skill_id and ("blood_pact" in action.skill_id or "circle" in action.skill_id
                             or "ward" in action.skill_id or "block" in action.skill_id
                             or "unbreakable" in action.skill_id)
    )


#: Сколько бойцов живая группа отправит на объект - остальные бьют босса.
_HELPERS = {rf.HANDS: 3, rf.GRAVE: 2, rf.CHAIN: 2, rf.BELL: 2}


def _smart_stage2(actor, session, stage: rf.SummonerStage):
    """Раздача по порядку: первые свободные идут к самому срочному объекту,
    пока он не набрал нужное число рук, дальше - к следующему, остальные
    бьют призывателя. Курган бьют все, кто его ещё не бил."""
    alive = {o.kind: o for o in stage.objects if session.combatants[o.combatant_id].alive}
    mound = alive.get(rf.MOUND)
    if mound is not None:
        if actor.id not in mound.hitters:
            return session.combatants[mound.combatant_id]
    living = [p for p in session.combatants.values() if p.kind == "character" and p.alive]
    queue = []
    for kind in (rf.HANDS, rf.GRAVE, rf.CHAIN, rf.BELL):
        obj = alive.get(kind)
        if obj is not None:
            queue.extend([obj] * _HELPERS[kind])
    slot = 0
    for p in living:
        if any(o.kind == rf.HANDS and o.victim_id == p.id for o in alive.values()):
            continue
        if p.id == actor.id:
            if slot < len(queue):
                return session.combatants[queue[slot].combatant_id]
            break
        slot += 1
    return session.combatants[stage.summoner_id]


def _smart_stage3(actor, session, stage: rf.GeneralStage, order: int) -> DeclaredAction:
    general = session.combatants[stage.general_id]
    action = _attack(actor, session, general)
    shown = stage.announced
    hits_general = _is_offensive_on(action, general.id)
    skip = DeclaredAction(type=ActionType.SKIP)
    if shown == rf.GUARD and hits_general:
        return skip
    if shown == rf.COUNT and hits_general and order >= stage.count_allowed:
        return skip
    if shown == rf.IRON and action.type == ActionType.ATTACK:
        return skip
    if shown == rf.CHALLENGE and hits_general and actor.id != stage.ai.target_id:
        return skip
    return action


def run(size: int, smart: bool, rng: random.Random) -> dict:
    players = _party(size)
    out = {"won": False, "stage": 1, "ticks": [0, 0, 0], "deaths": 0, "leftover": 0}
    damage_by: dict[int, int] = {}
    leftover = 0
    for stage_no in (1, 2, 3):
        out["stage"] = stage_no
        _fresh(players)
        session = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
        for p in players:
            session.add(p)
        if stage_no == 1:
            stage = rf.FogStage(20_300_000)
        elif stage_no == 2:
            stage = rf.SummonerStage(20_400_000, size)
        else:
            stage = rf.GeneralStage(20_500_000, leftover)
        stage.setup(session)
        frozen: list[int] = []
        cleared = False
        for _ in range(MAX_TICKS):
            session.tick_number += 1
            actions = {}
            living = [p for p in players if p.alive]
            for order, p in enumerate(living):
                if p.id in frozen:
                    continue
                if not smart:
                    target = pick_target(p, session)
                    if target is not None:
                        actions[p.id] = _attack(p, session, target)
                    continue
                if stage_no == 1:
                    bearers = [session.combatants[c] for c in stage.bearer_ids if session.combatants[c].alive]
                    target = min(bearers, key=lambda c: c.current_hp) if bearers else pick_target(p, session)
                    actions[p.id] = _attack(p, session, target)
                elif stage_no == 2:
                    actions[p.id] = _attack(p, session, _smart_stage2(p, session, stage))
                else:
                    actions[p.id] = _smart_stage3(p, session, stage, order)
            result = resolve_tick(session, actions, rng)
            for h in result.hit_renders:
                if h.source_side == 0 and h.target_side == 1 and not h.missed:
                    damage_by[h.source_id] = damage_by.get(h.source_id, 0) + h.amount
            out["ticks"][stage_no - 1] += 1
            if stage_no == 3:
                tick = stage.after_tick(session, result, rng, damage_by)
            elif stage_no == 2:
                tick = stage.after_tick(session, result, rng)
            else:
                tick = stage.after_tick(session, result)
            frozen = tick.frozen
            out["deaths"] += len([d for d in result.deaths if session.combatants[d].kind == "character"])
            out["deaths"] += len(tick.deaths)
            if not any(p.alive for p in players):
                return out
            if tick.cleared or (result.finished and result.winner_side == 0):
                cleared = True
                break
        if not cleared:
            return out
        if stage_no == 2:
            leftover = stage.leftover
            out["leftover"] = leftover
    out["won"] = True
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=60)
    parser.add_argument("--size", type=int, default=5)
    args = parser.parse_args()
    rng = random.Random(77)
    for smart in (True, False):
        runs = [run(args.size, smart, rng) for _ in range(args.rounds)]
        won = [r for r in runs if r["won"]]
        name = "умная" if smart else "бездумная"
        print(f"группа {args.size}, тактика {name}: побед {len(won)}/{len(runs)}")
        stuck = {s: sum(1 for r in runs if not r["won"] and r["stage"] == s) for s in (1, 2, 3)}
        print(f"  поражения по этапам: {stuck}")
        for i in range(3):
            ticks = [r["ticks"][i] for r in runs if r["stage"] > i or r["won"]]
            if ticks:
                print(f"  этап {i + 1}: ходов в среднем {statistics.fmean(ticks):.1f}")
        print(f"  смертей за заход: {statistics.fmean(r['deaths'] for r in runs):.1f}"
              f", объектов к алебарде: {statistics.fmean(r['leftover'] for r in runs):.1f}")


if __name__ == "__main__":
    main()
