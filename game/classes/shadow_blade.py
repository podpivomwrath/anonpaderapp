"""Клинок теней / Ассасин — Разбойник, ДД (крит/бурст), дотягивается до Танка.

Кит патча 39, ч.3: Скользящий рез копит стаки «Метки добычи» (EffectKind.MARK)
на цели, Жатва меток тратит их на бонус-урон, Танец в тени (дженерик
self_dodge_buff, регистрируется в subclass_skills.py) — самоуворот, Казнь —
гарантированный крит с добивающим множителем по цели <30% HP.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat import shared_rules
from game.combat.session import EffectKind
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
    """Скользящий рез: 145% урона, +2 стака Метки добычи (макс. 5). Единственный
    способ открыть метку без баффов пресета: пассивка только добавляет к ней."""
    skill = SUBCLASS_SKILL_DEFS["shadow_blade_marked_strike"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))

    # Длительность обновляется до полной, не суммируется (патч 52, баг 1).
    shared_rules.add_mark(actor, target, bc.SHADOW_BLADE_MARKED_STRIKE_STACKS)
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
    # Патч 56, «Разделка»: если тратим достаточно стаков, крит бьёт сильнее.
    carve_mult = actor.buff_modifiers.get("carve_crit_mult", 0.0)
    crit_multiplier = (
        carve_mult
        if carve_mult > 0 and stacks >= bc.SHADOW_BLADE_CARVE_MIN_STACKS
        else None
    )
    ctx.hits.append(
        compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True,
                    crit_multiplier=crit_multiplier)
    )
    if mark is not None:
        target.effects.remove(mark)


@offensive_skill("shadow_blade_execute")
def execute(ctx: SkillContext) -> None:
    """Казнь: 195% урона, гарантированный крит. Если цель ниже 30% HP — урон удваивается."""
    skill = SUBCLASS_SKILL_DEFS["shadow_blade_execute"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    low_hp = target.current_hp < target.max_hp * bc.SHADOW_BLADE_EXECUTE_HP_THRESHOLD
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, force_crit=True, is_ability=True)
    if low_hp:
        hit.amount = round(hit.amount * bc.SHADOW_BLADE_EXECUTE_LOW_HP_MULT)
    ctx.hits.append(hit)
