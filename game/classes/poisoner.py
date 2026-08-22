"""Отравитель — Разбойник, Саппорт (дебафф/контроль), дотягивается до ДД.

Кит патча 39, ч.3: Отравленный клинок копит стаки Яда (EffectKind.DOT, как
раньше — на ЦЕЛЬ, не на атакующего), Разложение — дженерик Уязвимость
(effect="target_vuln" в JSON, регистрируется в subclass_skills.py),
Дурманящий дротик — шанс сбоя действия цели В ЭТОТ ЖЕ ход (зарегистрирован
как control-навык вручную ниже — шанс делает его НЕ дженерик-"stun"), Токсический
выброс — мгновенный урон от накопленного яда, снимает стаки (яд необорачиваем,
патч 34 — считается как ДоТ, не проходит через уворот/крит/митигацию).
"""

from game.combat import balance_config as bc
from game.combat import combat_flavor, control
from game.classes.base import Role, SubclassDef, register
from game.combat.session import CombatMode, Effect, EffectKind
from game.combat.skills import PendingHit, SkillContext, compute_hit, offensive_skill
import game.combat.subclass_skills as subclass_skills
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

POISONER = register(
    SubclassDef(
        id="poisoner",
        title="Отравитель",
        base_class="rogue",
        primary_stat="agi",
        natural_role=Role.SUPPORT,
        flexible_roles=(Role.DD,),
        skills=("attack", "poisoner_venom", "poisoner_decay", "poisoner_disrupt", "poisoner_toxic_burst"),
    )
)

# Дротик — контроль С ШАНСОМ (60%), поэтому не подходит под дженерик "stun"
# (тот всегда пытается наложить контроль); фазе резолвера всё равно нужно
# знать, что это control-навык — иначе цель успеет объявленно подействовать
# ДО того, как дротик решит, оглушать её или нет.
subclass_skills.CONTROL_SKILL_IDS.add("poisoner_disrupt")


def poison_tick_damage_per_stack(will: int, agility: int) -> float:
    """Сила яда масштабируется от статов; тик-урон = сила / макс. стаки."""
    poison_power = (
        bc.POISONER_POISON_WIL_COEF * will + bc.POISONER_POISON_AGI_COEF * agility
    )
    return poison_power / bc.POISONER_MAX_STACKS


@offensive_skill("poisoner_venom")
def venom(ctx: SkillContext) -> None:
    """Отравленный клинок: 105% урона + стак яда (ДоТ) НА ЦЕЛЬ (макс. 3)."""
    skill = SUBCLASS_SKILL_DEFS["poisoner_venom"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return

    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))

    per_stack = poison_tick_damage_per_stack(actor.stats.will, actor.stats.agility)
    # Патч 47: «Затяжной яд» — +duration_bonus ходов к длительности; 0 без баффа.
    duration = bc.POISONER_POISON_DURATION_TICKS + int(actor.buff_modifiers.get("poison_duration_bonus", 0))
    existing = target.effect_from(EffectKind.DOT, actor.id)
    if existing is not None:
        existing.stacks = min(existing.stacks + 1, bc.POISONER_MAX_STACKS)
        existing.value = per_stack
        # Патч 52, баг 1: длительность ОБНОВЛЯЕТСЯ до полной, не суммируется —
        # max() вместо прямого присваивания защищает от отката длительности
        # вниз, если пересчитанная duration вдруг окажется меньше остатка.
        existing.remaining_ticks = max(existing.remaining_ticks, duration)
    else:
        target.effects.append(
            Effect(kind=EffectKind.DOT, value=per_stack, remaining_ticks=duration,
                   source_id=actor.id, stacks=1)
        )
    ctx.lines.append(f"{target.name} под действием яда ({actor.name}) ☠")


@offensive_skill("poisoner_disrupt")
def disrupt(ctx: SkillContext) -> None:
    """Дурманящий дротик: 80% урона, 60% шанс сбить действие цели В ЭТОТ ход,
    Ослабление -25% урона цели на 3 хода (безусловно)."""
    skill = SUBCLASS_SKILL_DEFS["poisoner_disrupt"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return

    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))
    target.apply_effect(EffectKind.WEAKEN, 0.25, 3, actor.id)

    if ctx.rng.random() < skill.effect_value:
        pvp = ctx.session.mode != CombatMode.PVE
        res = control.try_apply_control(
            target, base_duration=bc.CONTROL_BASE_DURATION_TICKS, source_id=actor.id, rng=ctx.rng, pvp=pvp,
        )
        if res.immune:
            ctx.lines.append(combat_flavor.control_blocked_line(target.name))
        elif res.resisted:
            ctx.lines.append(combat_flavor.control_resisted_line(target.name))
        # Патч 52, баг 1: успешное наложение — «теряет ход» не печатается
        # здесь, единственное место теперь резолвер (game/combat/resolver.py).


@offensive_skill("poisoner_toxic_burst")
def toxic_burst(ctx: SkillContext) -> None:
    """Токсический выброс: мгновенный урон = 250% суммарного тик-урона яда на
    цели, снимает все стаки Яда. Как и ДоТ — не проходит через уворот/крит."""
    skill = SUBCLASS_SKILL_DEFS["poisoner_toxic_burst"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    poison = target.effect_from(EffectKind.DOT, actor.id)
    if poison is None:
        ctx.lines.append(f"{actor.name} бьёт впустую — на {target.name} нет яда")
        return
    tick_damage = poison.value * poison.stacks
    amount = max(round(tick_damage * skill.effect_value), 1)
    ctx.hits.append(PendingHit(source_id=actor.id, target_id=target.id, amount=amount, label="взрывает ядом", is_dot=True))
    target.effects.remove(poison)
