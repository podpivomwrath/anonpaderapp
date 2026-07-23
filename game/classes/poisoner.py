"""Отравитель — Разбойник, Саппорт (дебафф/контроль), дотягивается до ДД.

Яд реализован по патчу балансировки: сила яда ОБЯЗАНА масштабироваться
от статов (0.60×WIL + 0.40×AGI на стак, тик-урон делится на макс. стаки),
прямой урон со штрафом ×0.90.

ВНИМАНИЕ (баг из балансировочного теста): яд накладывается на ЦЕЛЬ,
не на атакующего — регрессионный тест в tests/test_calibration.py.

TODO: content — Уязвимость/Ослабление на стаках яда и «сбой» действия
отравленной цели (poisoner_disrupt) не калибровались, значения позже.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import Effect, EffectKind
from game.combat.skills import SkillContext, compute_hit, offensive_skill

POISONER = register(
    SubclassDef(
        id="poisoner",
        title="Отравитель",
        base_class="rogue",
        primary_stat="agi",
        natural_role=Role.SUPPORT,
        flexible_roles=(Role.DD,),
        skills=("attack", "poisoner_venom", "poisoner_disrupt"),
    )
)


def poison_tick_damage_per_stack(will: int, agility: int) -> float:
    """Сила яда масштабируется от статов; тик-урон = сила / макс. стаки."""
    poison_power = (
        bc.POISONER_POISON_WIL_COEF * will + bc.POISONER_POISON_AGI_COEF * agility
    )
    return poison_power / bc.POISONER_MAX_STACKS


@offensive_skill("poisoner_venom")
def venom(ctx: SkillContext) -> None:
    """Ядовитый удар: прямой урон ×0.90 + стак яда (ДоТ) НА ЦЕЛЬ."""
    target = ctx.resolve_target()
    if target is None:
        return

    hit = compute_hit(ctx.actor, target, ctx.rng, label="жалит")
    hit.amount = max(round(hit.amount * bc.POISONER_DIRECT_MULT), 1)
    ctx.hits.append(hit)

    per_stack = poison_tick_damage_per_stack(ctx.actor.stats.will, ctx.actor.stats.agility)
    # стак вешается на TARGET (не на атакующего — см. докстринг)
    existing = next(
        (
            e
            for e in target.effects_of(EffectKind.DOT)
            if e.source_id == ctx.actor.id
        ),
        None,
    )
    if existing is not None:
        existing.stacks = min(existing.stacks + 1, bc.POISONER_MAX_STACKS)
        existing.value = per_stack
        existing.remaining_ticks = bc.POISONER_POISON_DURATION_TICKS  # обновление
    else:
        target.effects.append(
            Effect(
                kind=EffectKind.DOT,
                value=per_stack,
                remaining_ticks=bc.POISONER_POISON_DURATION_TICKS,
                source_id=ctx.actor.id,
                stacks=1,
            )
        )
    ctx.lines.append(f"{target.name} отравлен ({ctx.actor.name}) ☠")


# TODO: content
# @offensive_skill("poisoner_disrupt") — шанс сбоя действия отравленной цели
#   (через control_resist от WIL цели)
