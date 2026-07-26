"""Страж (Guardian) — Воин, естественная роль: Танк (дотягивается до Саппорта).

РЕФЕРЕНСНЫЙ подкласс: полностью реализован, остальные 5 — по этой же структуре.

Механики (без позиционирования, тиковая боёвка):
  - Блок — реактивная защита, срезает входящий урон в этот же тик;
  - Провокация — PvE: жёсткий форс цели мобов (мобы ходят после игроков);
    PvP: дебаф «урон по другим целям снижен, если враг не бил провоцирующего»;
  - Групповой щит — часть защиты уходит союзнику с наименьшим % HP.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import CombatMode, Effect, EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, defensive_skill

GUARDIAN = register(
    SubclassDef(
        id="guardian",
        title="Страж",
        base_class="warrior",
        primary_stat="str",
        natural_role=Role.TANK,
        flexible_roles=(Role.SUPPORT,),
        skills=("attack", "guardian_block", "guardian_provoke", "guardian_group_shield"),
    )
)


@defensive_skill("guardian_block")
def block(ctx: SkillContext) -> None:
    """Блок: снижает входящий урон этого тика. Микробаффы активного пресета
    (патч 14, ч.3) добавляют: шанс ПОЛНОГО блока (Несокрушимость), самоисцеление
    при блоке (Живительный блок), контрудар (Возмездие)."""
    actor = ctx.actor
    full_block_chance = actor.buff_modifiers.get("full_block_chance", 0.0)
    if full_block_chance > 0 and ctx.rng.random() < full_block_chance:
        actor.block_reduction = 1.0
        ctx.lines.append(f"{actor.name} блокирует удар ПОЛНОСТЬЮ 🛡✨")
    else:
        actor.block_reduction = max(actor.block_reduction, bc.GUARDIAN_BLOCK_REDUCTION)
        ctx.lines.append(f"{actor.name} поднимает щит (блок) 🛡")

    heal_pct = actor.buff_modifiers.get("heal_on_block_pct_max_hp", 0.0)
    if heal_pct > 0:
        ctx.heals.append(
            PendingHeal(
                source_id=actor.id, target_id=actor.id,
                amount=round(actor.max_hp * heal_pct), label="исцеляется от блока",
            )
        )

    counterstrike_mult = actor.buff_modifiers.get("counterstrike_mult", 0.0)
    if counterstrike_mult > 0:
        enemies = ctx.session.alive_enemies_of(actor)
        if enemies:
            target = ctx.rng.choice(enemies)
            ctx.hits.append(
                compute_hit(actor, target, ctx.rng, label="контратакует", multiplier=counterstrike_mult)
            )


@defensive_skill("guardian_provoke")
def provoke(ctx: SkillContext) -> None:
    """Провокация: PvE — форс цели мобов, PvP — дебаф на урон по другим целям."""
    enemies = ctx.session.alive_enemies_of(ctx.actor)
    if ctx.session.mode == CombatMode.PVE:
        for enemy in enemies:
            if enemy.kind == "mob":
                enemy.taunted_by = ctx.actor.id
        ctx.lines.append(f"{ctx.actor.name} провоцирует врагов — цели мобов форсированы!")
    else:
        for enemy in enemies:
            enemy.effects.append(
                Effect(
                    kind=EffectKind.PROVOKE_PVP,
                    value=bc.PROVOKE_PVP_DAMAGE_REDUCTION,
                    remaining_ticks=bc.PROVOKE_PVP_DURATION_TICKS,
                    source_id=ctx.actor.id,
                )
            )
        ctx.lines.append(
            f"{ctx.actor.name} провоцирует: урон противников по другим целям снижен"
        )


@defensive_skill("guardian_group_shield")
def group_shield(ctx: SkillContext) -> None:
    """Групповой щит: часть защиты уходит союзнику с наименьшим % HP."""
    allies = ctx.session.alive_allies_of(ctx.actor)
    target = min(allies, key=lambda c: c.current_hp / c.max_hp) if allies else ctx.actor
    absorb = round(ctx.actor.stats.vitality * bc.GUARDIAN_SHIELD_PER_VIT)
    target.shield += absorb
    if target.id != ctx.actor.id:
        # отдал часть своей защиты — штраф к собственной митигации в этот тик
        ctx.actor.mitigation_penalty = bc.GUARDIAN_SHIELD_SELF_PENALTY
    ctx.lines.append(f"{ctx.actor.name} накрывает щитом {target.name} (+{absorb} поглощения)")
