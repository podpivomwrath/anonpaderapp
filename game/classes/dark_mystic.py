"""Тёмный мистик — Маг, ЕДИНСТВЕННЫЙ хилер (осознанное решение дизайна:
престижная роль топового рейд-контента). Дотягивается до ДД и лёгкого Танка.

Кит патча 39, ч.3: Кровавый пакт — прямой урон, часть конвертируется в
исцеление; Оберег — щит (EffectKind.SHIELD_POOL, остаток превращается в
лечение при истечении — уже существующая логика resolver.py, патч 16);
Иссушение — урон+хил, усилен по контролируемой цели; Круг тьмы — себестоимость
HP, массовое исцеление союзников (вне группы лечит себя вдвое сильнее).
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

DARK_MYSTIC = register(
    SubclassDef(
        id="dark_mystic",
        title="Тёмный мистик",
        base_class="mage",
        primary_stat="int",
        natural_role=Role.HEALER,
        flexible_roles=(Role.DD, Role.TANK),
        skills=(
            "attack", "dark_mystic_blood_pact", "dark_mystic_ward",
            "dark_mystic_drain", "dark_mystic_circle",
        ),
    )
)


def _lowest_hp_ally_or_self(ctx: SkillContext):
    allies = ctx.session.alive_allies_of(ctx.actor)
    return min(allies, key=lambda c: c.current_hp / c.max_hp) if allies else ctx.actor


@offensive_skill("dark_mystic_blood_pact")
def blood_pact(ctx: SkillContext) -> None:
    """Кровавый пакт: 110% урона цели, 70% нанесённого — лечением союзнику с
    наименьшим HP (себе, если союзника нет)."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_blood_pact"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    heal = max(round(hit.amount * skill.effect_value), 1)
    heal_target = _lowest_hp_ally_or_self(ctx)
    ctx.heals.append(PendingHeal(source_id=actor.id, target_id=heal_target.id, amount=heal, label="исцеляет тьмой"))


@offensive_skill("dark_mystic_ward")
def ward(ctx: SkillContext) -> None:
    """Оберег: без урона, щит себе или союзнику (масштаб от Воли), 3 хода,
    остаток по истечении превращается в лечение (resolver.py, как «Второе
    сердце» — патч 16)."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_ward"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    ward_target = _lowest_hp_ally_or_self(ctx)
    absorb = round(formulas.support_power(actor.stats.will) * bc.DARK_MYSTIC_WARD_SHIELD_COEF)
    ward_target.apply_effect(EffectKind.SHIELD_POOL, absorb, skill.effect_duration, actor.id)
    ctx.lines.append(f"{actor.name} накрывает {ward_target.name} Оберегом (+{absorb} поглощения)")


@offensive_skill("dark_mystic_drain")
def drain(ctx: SkillContext) -> None:
    """Иссушение: 160% урона, лечит на 50% нанесённого. Цель под контролем — урон +40%."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_drain"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    multiplier = skill.multiplier * 1.4 if target.has_effect(EffectKind.FREEZE) else skill.multiplier
    hit = compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True)
    ctx.hits.append(hit)
    heal = max(round(hit.amount * skill.effect_value), 1)
    ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id, amount=heal, label="исцеляется иссушением"))


@offensive_skill("dark_mystic_circle")
def circle_of_dark(ctx: SkillContext) -> None:
    """Круг тьмы: тратит 20% текущего HP, лечит всех союзников на 180% силы
    поддержки. Вне группы лечит себя вдвое сильнее."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_circle"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    cost = round(actor.current_hp * bc.DARK_MYSTIC_CIRCLE_HP_COST)
    actor.current_hp = max(actor.current_hp - cost, 1)

    power = formulas.support_power(actor.stats.will) * skill.effect_value
    allies = ctx.session.alive_allies_of(actor)
    if allies:
        for ally in allies:
            ctx.heals.append(PendingHeal(source_id=actor.id, target_id=ally.id, amount=round(power), label="исцеляет кругом тьмы"))
    else:
        ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id, amount=round(power * 2), label="исцеляет кругом тьмы"))
