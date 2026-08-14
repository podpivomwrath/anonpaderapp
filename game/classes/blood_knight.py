"""Кровавый рыцарь (Blood Knight) — Воин, ДД (сустейн-лайфстил).

Кит патча 39, ч.3: Кровопуск (частый лайфстил, капается — иначе бесконтрольно
скейлится с уроном на высоких уровнях), Жатва (бонус-хил при низком HP),
Кровавая печать (метка цели — удваивает лайфстил ЛЮБОЙ последующей атаки
рыцаря по ней на 3 хода), Багровый пир (себестоимость HP, крупный бурст+хил).
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

BLOOD_KNIGHT = register(
    SubclassDef(
        id="blood_knight",
        title="Кровавый рыцарь",
        base_class="warrior",
        primary_stat="str",
        natural_role=Role.DD,
        flexible_roles=(Role.TANK, Role.SUPPORT),
        skills=(
            "attack", "blood_knight_lifesteal_strike", "blood_knight_harvest",
            "blood_knight_blood_seal", "blood_knight_crimson_feast",
        ),
    )
)


def _lifesteal_heal(ctx: SkillContext, hit, ratio: float, cap_pct: float | None) -> None:
    """Лечение от лайфстила: удваивается, если цель под Кровавой печатью
    этого рыцаря (EffectKind.BLOOD_SEAL), опционально капается % maxHP/тик."""
    actor = ctx.actor
    target = ctx.session.combatants.get(hit.target_id)
    if target is not None and target.effect_from(EffectKind.BLOOD_SEAL, actor.id) is not None:
        ratio *= 2
    heal = round(hit.amount * ratio)
    if cap_pct is not None:
        heal = min(heal, round(actor.max_hp * cap_pct))
    if heal > 0:
        ctx.heals.append(
            PendingHeal(source_id=actor.id, target_id=actor.id, amount=heal, label="восполняет кровью")
        )


@offensive_skill("blood_knight_lifesteal_strike")
def lifesteal_strike(ctx: SkillContext) -> None:
    """Кровопуск: 145% урона, лечит на 25% нанесённого (капается — самый
    частый навык кита, cd2)."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_lifesteal_strike"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    _lifesteal_heal(ctx, hit, skill.effect_value, bc.BLOOD_KNIGHT_HEAL_CAP_PER_TICK)


@offensive_skill("blood_knight_harvest")
def harvest(ctx: SkillContext) -> None:
    """Жатва: 190% урона. Если HP актёра ниже 50% — лечит на 40% нанесённого."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_harvest"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    if actor.current_hp < actor.max_hp * 0.5:
        _lifesteal_heal(ctx, hit, skill.effect_value, None)


@offensive_skill("blood_knight_blood_seal")
def blood_seal(ctx: SkillContext) -> None:
    """Кровавая печать: 100% урона, метит цель на 3 хода — все последующие
    атаки рыцаря по ней лечат вдвое сильнее."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_blood_seal"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))
    target.apply_effect(EffectKind.BLOOD_SEAL, 1.0, skill.effect_duration, actor.id)
    ctx.lines.append(f"{target.name} отмечен Кровавой печатью 🩸")


@offensive_skill("blood_knight_crimson_feast")
def crimson_feast(ctx: SkillContext) -> None:
    """Багровый пир: тратит 15% текущего HP, 260% урона, лечит на 60% нанесённого."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_crimson_feast"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    cost = round(actor.current_hp * bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)
    actor.current_hp = max(actor.current_hp - cost, 1)
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    _lifesteal_heal(ctx, hit, skill.effect_value, None)
