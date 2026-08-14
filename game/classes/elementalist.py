"""Элементалист — Маг, ДД (стихийный урон), дотягивается до Саппорта (контроль).

Кит патча 39, ч.3: Огненная плеть вешает Горение (EffectKind.DOT, магнитуда —
доля от урона самого удара), Ледяные оковы — дженерик оглушение (effect="stun"
в JSON, регистрируется в subclass_skills.py), Цепь молний бьёт по трём целям
разом, Схождение стихий усиливается Горением и критует гарантированно по
замороженной цели (упрощение: проверяем ТЕКУЩИЙ FREEZE, а не историю за
последние 2 хода — движок не хранит историю контроля дольше текущего эффекта)."""

from game.classes.base import Role, SubclassDef, register
from game.combat.session import EffectKind
from game.combat.skills import SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

ELEMENTALIST = register(
    SubclassDef(
        id="elementalist",
        title="Элементалист",
        base_class="mage",
        primary_stat="int",
        natural_role=Role.DD,
        flexible_roles=(Role.SUPPORT,),
        skills=(
            "attack", "elementalist_fire", "elementalist_ice",
            "elementalist_lightning", "elementalist_convergence",
        ),
    )
)


@offensive_skill("elementalist_fire")
def fire_whip(ctx: SkillContext) -> None:
    """Огненная плеть: 130% урона + Горение (ДоТ на 3 хода, магнитуда —
    доля от урона этого удара)."""
    skill = SUBCLASS_SKILL_DEFS["elementalist_fire"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    burn_value = max(hit.amount * skill.effect_value, 1.0)
    target.apply_effect(EffectKind.DOT, burn_value, skill.effect_duration, actor.id)
    ctx.lines.append(f"{target.name} охвачен пламенем 🔥")


@offensive_skill("elementalist_lightning")
def chain_lightning(ctx: SkillContext) -> None:
    """Цепь молний: 115% урона основной цели, 60% от этого — ещё двум противникам."""
    skill = SUBCLASS_SKILL_DEFS["elementalist_lightning"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))

    others = [e for e in ctx.session.alive_enemies_of(actor) if e.id != target.id]
    ctx.rng.shuffle(others)
    for extra in others[:2]:
        ctx.hits.append(
            compute_hit(actor, extra, ctx.rng, skill.name, skill.multiplier * skill.effect_value, is_ability=True)
        )


@offensive_skill("elementalist_convergence")
def convergence(ctx: SkillContext) -> None:
    """Схождение стихий: 240% урона. Есть Горение от этого элементалиста —
    +60% урона; цель заморожена — гарантированный крит."""
    skill = SUBCLASS_SKILL_DEFS["elementalist_convergence"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    multiplier = skill.multiplier
    if target.effect_from(EffectKind.DOT, actor.id) is not None:
        multiplier *= 1.0 + skill.effect_value
    force_crit = target.has_effect(EffectKind.FREEZE)
    ctx.hits.append(
        compute_hit(actor, target, ctx.rng, skill.name, multiplier, force_crit=force_crit, is_ability=True)
    )
