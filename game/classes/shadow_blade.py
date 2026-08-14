"""Клинок теней / Ассасин — Разбойник, ДД (крит/бурст), дотягивается до Танка.

Кит патча 39, ч.3: Скользящий рез копит стаки «Метки добычи» (EffectKind.MARK)
на цели, Жатва меток тратит их на бонус-урон, Танец в тени (дженерик
self_dodge_buff, регистрируется в subclass_skills.py) — самоуворот, Казнь —
гарантированный крит с добивающим множителем по цели <30% HP.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import Effect, EffectKind
from game.combat.skills import SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

SHADOW_BLADE = register(
    SubclassDef(
        id="shadow_blade",
        title="Клинок теней",
        base_class="rogue",
        primary_stat="agi",
        natural_role=Role.DD,
        flexible_roles=(Role.TANK,),
        skills=(
            "attack", "shadow_blade_marked_strike", "shadow_blade_mark_harvest",
            "shadow_blade_shadow_dance", "shadow_blade_execute",
        ),
    )
)


@offensive_skill("shadow_blade_marked_strike")
def marked_strike(ctx: SkillContext) -> None:
    """Скользящий рез: 135% урона, +1 стак Метки добычи (макс. 5)."""
    skill = SUBCLASS_SKILL_DEFS["shadow_blade_marked_strike"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))

    existing = target.effect_from(EffectKind.MARK, actor.id)
    if existing is not None:
        existing.stacks = min(existing.stacks + 1, bc.SHADOW_BLADE_MARK_MAX_STACKS)
        existing.remaining_ticks = bc.SHADOW_BLADE_MARK_DURATION
    else:
        target.effects.append(
            Effect(kind=EffectKind.MARK, value=1.0, remaining_ticks=bc.SHADOW_BLADE_MARK_DURATION,
                   source_id=actor.id, stacks=1)
        )
    ctx.lines.append(f"{target.name} помечен добычей ({actor.name}) 🎯")


@offensive_skill("shadow_blade_mark_harvest")
def mark_harvest(ctx: SkillContext) -> None:
    """Жатва меток: 120% + 35% за каждый стак Метки, тратит все стаки."""
    skill = SUBCLASS_SKILL_DEFS["shadow_blade_mark_harvest"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    mark = target.effect_from(EffectKind.MARK, actor.id)
    stacks = mark.stacks if mark is not None else 0
    multiplier = skill.multiplier + skill.effect_value * stacks
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True))
    if mark is not None:
        target.effects.remove(mark)


@offensive_skill("shadow_blade_execute")
def execute(ctx: SkillContext) -> None:
    """Казнь: 200% урона, гарантированный крит. Если цель ниже 30% HP — урон удваивается."""
    skill = SUBCLASS_SKILL_DEFS["shadow_blade_execute"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    low_hp = target.current_hp < target.max_hp * 0.3
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, force_crit=True, is_ability=True)
    if low_hp:
        hit.amount *= 2
    ctx.hits.append(hit)
