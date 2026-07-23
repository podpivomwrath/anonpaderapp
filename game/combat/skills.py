"""Реестр боевых умений и расчёт удара.

Умения делятся на две фазы тика:
  - защитные (DEFENSIVE) — применяются ПЕРВЫМИ и защищают уже в этот тик;
  - атакующие (OFFENSIVE) — считаются по состоянию после защитной фазы,
    применяются одновременно в фазу применения.

Подклассы регистрируют свои умения декораторами при импорте модуля
(см. game/classes/__init__.py).
"""

import random
from dataclasses import dataclass, field
from typing import Callable

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import (
    CombatantState,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)


@dataclass
class PendingHit:
    source_id: int
    target_id: int
    amount: int
    crit: bool = False
    label: str = "бьёт"
    missed: bool = False  # цель полностью уклонилась (Дымовая завеса)
    is_dot: bool = False  # периодический урон (яд/горение) — для атмосферного лога


@dataclass
class PendingHeal:
    source_id: int
    target_id: int
    amount: int
    label: str = "исцеляет"


@dataclass
class SkillContext:
    session: CombatSessionState
    actor: CombatantState
    action: DeclaredAction
    rng: random.Random
    hits: list[PendingHit] = field(default_factory=list)
    heals: list[PendingHeal] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def resolve_target(self) -> CombatantState | None:
        """Цель действия: указанная живая, иначе случайный живой враг."""
        target_id = self.action.target_id
        if target_id is not None:
            target = self.session.combatants.get(target_id)
            if target is not None and target.alive:
                return target
        enemies = self.session.alive_enemies_of(self.actor)
        return self.rng.choice(enemies) if enemies else None


SkillHandler = Callable[[SkillContext], None]

DEFENSIVE_SKILLS: dict[str, SkillHandler] = {}
OFFENSIVE_SKILLS: dict[str, SkillHandler] = {}


def defensive_skill(skill_id: str) -> Callable[[SkillHandler], SkillHandler]:
    def wrap(fn: SkillHandler) -> SkillHandler:
        DEFENSIVE_SKILLS[skill_id] = fn
        return fn

    return wrap


def offensive_skill(skill_id: str) -> Callable[[SkillHandler], SkillHandler]:
    def wrap(fn: SkillHandler) -> SkillHandler:
        OFFENSIVE_SKILLS[skill_id] = fn
        return fn

    return wrap


# --- Расчёт удара (общий для tick_engine и duel_engine) ---


DODGE_CAP = 0.95  # даже с баффом остаётся шанс попасть


def outgoing_multiplier(actor: CombatantState, target: CombatantState) -> float:
    """Модификаторы исходящего урона: Ослабление, Боевой клич, PvP-провокация."""
    mult = 1.0 - min(actor.effect_total(EffectKind.WEAKEN), 0.9)
    mult *= 1.0 + actor.effect_total(EffectKind.DAMAGE_BUFF)  # Боевой клич +30%
    for effect in actor.effects_of(EffectKind.PROVOKE_PVP):
        if target.id != effect.source_id:
            mult *= 1.0 - effect.value
    return max(mult, 0.0)


def effective_mitigation(target: CombatantState) -> float:
    """Митигация с учётом штрафа (групповой щит стража отдаёт часть защиты)."""
    base = formulas.mitigation(target.stats.vitality)
    return base * (1.0 - target.mitigation_penalty)


def compute_hit(
    actor: CombatantState,
    target: CombatantState,
    rng: random.Random,
    label: str = "бьёт",
    multiplier: float = 1.0,
    force_crit: bool = False,
) -> PendingHit:
    """Расчёт удара. multiplier — множитель урона навыка (Атака = 1.0);
    force_crit — гарантированный крит (Теневой рывок)."""
    # Уклонение цели (Дымовая завеса) — полностью гасит удар
    dodge = min(target.effect_total(EffectKind.DODGE), DODGE_CAP)
    if dodge > 0 and rng.random() < dodge:
        return PendingHit(
            source_id=actor.id, target_id=target.id, amount=0, label=label, missed=True
        )

    base = formulas.damage(
        actor.tier_mult,
        actor.stats.by_key(actor.primary_stat),
        formulas.k_dmg_for(actor.primary_stat),
    ) * multiplier
    crit = True if force_crit else rng.random() < formulas.crit_chance(actor.stats.agility)
    if crit:
        base *= bc.CRIT_MULTIPLIER
    base *= outgoing_multiplier(actor, target)
    base *= 1.0 + target.effect_total(EffectKind.VULNERABILITY)
    base *= 1.0 - effective_mitigation(target)
    base *= 1.0 - target.block_reduction
    return PendingHit(
        source_id=actor.id,
        target_id=target.id,
        amount=max(round(base), 1),
        crit=crit,
        label=label,
    )


@offensive_skill("attack")
def basic_attack(ctx: SkillContext) -> None:
    """Базовая атака — доступна всем."""
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(ctx.actor, target, ctx.rng))
