"""Прикидка лечения и щитов навыка для карточки руны (2026-11-11, владелец:
у «Круга тьмы» не было видно, от чего и на сколько он лечит).

Числа не пересчитываются отдельной формулой - навык прогоняется настоящим
обработчиком (shared_rules.run_skill) в пробном бою: с мастерством,
ступенями, огранками и пассивкой героя. Без случайностей: шансы не
срабатывают, крита нет.

Два прогона: «в одиночку» (герой ранен, против манекена) и «в группе» (с ним
такой же союзник, раненый сильнее - большинство навыков поддержки выбирают
самого раненого).
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    Stats,
)


class _NoLuck(random.Random):
    """Шансы не срабатывают, выбор - первый."""

    def random(self) -> float:
        return 0.999

    def choice(self, seq):
        return seq[0]


@dataclass
class Preview:
    heal_solo: int = 0      # себе, в одиночку
    heal_self: int = 0      # себе, в группе
    heal_ally: int = 0      # союзнику, в группе
    shield_solo: int = 0
    shield_self: int = 0
    shield_ally: int = 0
    cost: int = 0           # здоровья заплачено (в одиночку, с полного)
    hit: int = 0            # удар навыка по манекену без брони (в одиночку)
    block_heal: int = 0     # «Глухая оборона»: лечение за каждый удар в стойку
    shield_low: int = 0     # щит, когда герой почти при смерти (15% здоровья, в одиночку)
    lines: list[str] = field(default_factory=list)


def _dummy(level: int):
    from game.combat.session import build_combatant

    zero = Stats(strength=0, agility=0, intellect=0, vitality=0, will=0)
    dummy = build_combatant(id=900, side=1, kind="mob", name="Манекен", level=level, stats=zero,
                            primary_stat="str")
    dummy.max_hp = dummy.current_hp = 10 ** 7
    return dummy


def _run(hero, allies: list, skill_id: str) -> tuple[dict, dict, int, int]:
    """(лечение по id, щиты по id, сколько герой заплатил здоровьем, удар)."""
    from game.combat import shared_rules
    from game.combat.skills import DEFENSIVE_SKILLS, OFFENSIVE_SKILLS, SkillContext

    handler = OFFENSIVE_SKILLS.get(skill_id) or DEFENSIVE_SKILLS.get(skill_id)
    session = CombatSessionState(session_id=0, mode=CombatMode.PVE)
    dummy = _dummy(hero.level)
    for c in [hero, *allies, dummy]:
        session.add(c)
    action = DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=dummy.id)
    ctx = SkillContext(session=session, actor=hero, action=action, rng=_NoLuck())
    hp_before = hero.current_hp
    shields_before = {c.id: sum(e.value for e in c.effects if e.kind == EffectKind.SHIELD_POOL)
                      for c in session.combatants.values()}
    shared_rules.run_skill(handler, ctx, skill_id)
    heals: dict[int, int] = {}
    for h in ctx.heals:
        if h.source_id != hero.id:
            continue
        amount = h.amount
        if h.of_hit is not None and h.ratio:
            amount = max(round(h.of_hit.amount * h.ratio), h.floor)
        heals[h.target_id] = heals.get(h.target_id, 0) + max(amount, 0)
    shields = {}
    for c in session.combatants.values():
        now = sum(e.value for e in c.effects if e.kind == EffectKind.SHIELD_POOL)
        if now > shields_before[c.id]:
            shields[c.id] = round(now - shields_before[c.id])
    hit = max((h.amount for h in ctx.hits if h.source_id == hero.id and h.target_id == dummy.id
               and not h.missed), default=0)
    return heals, shields, max(hp_before - hero.current_hp, 0), hit


def preview(hero, skill_id: str) -> Preview:
    """hero - боец героя (его не меняем: прогоны идут на копиях)."""
    out = Preview()
    full = copy.deepcopy(hero)
    full.id, full.side, full.cooldowns = 1, 0, {}
    full.current_hp = full.max_hp  # цена здоровьем и удар - с полного
    _heals, _shields, out.cost, out.hit = _run(full, [], skill_id)
    out.block_heal = round(full.max_hp * full.effect_total(EffectKind.BLOCK_HEAL))

    # «Сомкнуть ряды» (репорт 350): щит почти вдвое крепче, если кто-то из
    # своих ниже порога, - карточке нужны оба числа.
    low = copy.deepcopy(hero)
    low.id, low.side, low.cooldowns = 1, 0, {}
    low.current_hp = round(low.max_hp * 0.15)
    _heals, shields, _cost, _hit = _run(low, [], skill_id)
    out.shield_low = shields.get(1, 0)

    solo = copy.deepcopy(hero)
    solo.id, solo.side, solo.cooldowns = 1, 0, {}
    solo.current_hp = round(solo.max_hp * 0.45)  # раненый: «Жатва» лечит ниже половины
    heals, shields, _cost, _hit = _run(solo, [], skill_id)
    out.heal_solo, out.shield_solo = heals.get(1, 0), shields.get(1, 0)

    me, ally = copy.deepcopy(hero), copy.deepcopy(hero)
    me.id, me.side, me.cooldowns = 1, 0, {}
    ally.id, ally.side, ally.cooldowns, ally.name = 2, 0, {}, "Союзник"
    # герой ранен меньше союзника, но ниже половины: «Жатва» лечит только так
    me.current_hp = round(me.max_hp * 0.45)
    ally.current_hp = round(ally.max_hp * 0.3)
    heals, shields, _cost, _hit = _run(me, [ally], skill_id)
    out.heal_self, out.heal_ally = heals.get(1, 0), heals.get(2, 0)
    out.shield_self, out.shield_ally = shields.get(1, 0), shields.get(2, 0)
    return out
