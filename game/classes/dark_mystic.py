"""Тёмный мистик — Маг, ЕДИНСТВЕННЫЙ хилер (осознанное решение дизайна:
престижная роль топового рейд-контента). Дотягивается до ДД и лёгкого Танка.

«Кровавый пакт» реализован по патчу балансировки: прямой урон ×0.76,
конверсия в исцеление support_power(WIL)×1.75 + 0.33. Осознанно НЕ
подтягивать выше для побед в чистых дуэлях — компенсация идёт через гир.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill

DARK_MYSTIC = register(
    SubclassDef(
        id="dark_mystic",
        title="Тёмный мистик",
        base_class="mage",
        primary_stat="int",
        natural_role=Role.HEALER,
        flexible_roles=(Role.DD, Role.TANK),
        skills=("attack", "dark_mystic_blood_pact"),
    )
)


def heal_conversion(will: int) -> float:
    """Доля урона пакта, уходящая лечением."""
    return (
        formulas.support_power(will) * bc.DARK_MYSTIC_HEAL_CONVERSION_COEF
        + bc.DARK_MYSTIC_HEAL_CONVERSION_BASE
    )


@offensive_skill("dark_mystic_blood_pact")
def blood_pact(ctx: SkillContext) -> None:
    """Тьма-урон цели; часть эффекта уходит лечением союзнику с наименьшим
    % HP; без союзника мистик лечит самого себя."""
    target = ctx.resolve_target()
    if target is None:
        return

    hit = compute_hit(ctx.actor, target, ctx.rng, label="поражает тьмой")
    hit.amount = max(round(hit.amount * bc.DARK_MYSTIC_PACT_MULT), 1)
    ctx.hits.append(hit)

    heal = max(round(hit.amount * heal_conversion(ctx.actor.stats.will)), 1)
    allies = ctx.session.alive_allies_of(ctx.actor)
    heal_target = (
        min(allies, key=lambda c: c.current_hp / c.max_hp) if allies else ctx.actor
    )
    ctx.heals.append(
        PendingHeal(
            source_id=ctx.actor.id,
            target_id=heal_target.id,
            amount=heal,
            label="исцеляет тьмой",
        )
    )
