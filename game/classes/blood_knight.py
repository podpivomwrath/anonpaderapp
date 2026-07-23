"""Кровавый рыцарь (Blood Knight) — Воин, ДД (сустейн-лайфстил).

Базовое действие реализовано по откалиброванным значениям патча балансировки:
лайфстил 9% от нанесённого урона (+3% при HP ниже 50%), кап лечения
8% maxHP за тик — кап обязателен, иначе лайфстил бесконтрольно скейлится.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill

BLOOD_KNIGHT = register(
    SubclassDef(
        id="blood_knight",
        title="Кровавый рыцарь",
        base_class="warrior",
        primary_stat="str",
        natural_role=Role.DD,
        flexible_roles=(Role.TANK, Role.SUPPORT),
        skills=("attack", "blood_knight_lifesteal_strike"),
    )
)


@offensive_skill("blood_knight_lifesteal_strike")
def lifesteal_strike(ctx: SkillContext) -> None:
    """Удар с лайфстилом: урон + лечение себе в один тик."""
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(ctx.actor, target, ctx.rng, label="рубит с лайфстилом")
    ctx.hits.append(hit)

    ratio = bc.BLOOD_KNIGHT_LIFESTEAL_BASE
    if ctx.actor.current_hp < ctx.actor.max_hp * bc.BLOOD_KNIGHT_LIFESTEAL_LOW_HP_THRESHOLD:
        ratio += bc.BLOOD_KNIGHT_LIFESTEAL_LOW_HP_BONUS
    heal = round(hit.amount * ratio)
    heal = min(heal, round(ctx.actor.max_hp * bc.BLOOD_KNIGHT_HEAL_CAP_PER_TICK))
    if heal > 0:
        ctx.heals.append(
            PendingHeal(
                source_id=ctx.actor.id,
                target_id=ctx.actor.id,
                amount=heal,
                label="восполняет кровью",
            )
        )
