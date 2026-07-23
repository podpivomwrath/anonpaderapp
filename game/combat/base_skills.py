"""Базовые навыки классов (combat-patch-2) — data-driven из content/skills.

Загружает base_skills.json и регистрирует по одному OFFENSIVE-хендлеру на навык.
Логика эффектов минимальна и общая; конкретные числа/тексты — в контенте.

КД навыка выставляется хендлером, тикает в резолвере/дуэли (ход = тик).
Эффекты контроля (оглушение/заморозка) подчиняются резисту от WIL цели.
Баффы/дебаффы non-stacking (apply_effect обновляет длительность, не суммирует).
"""

from game.combat import combat_flavor, control
from game.combat.session import CombatMode, EffectKind
from game.combat.skills import SkillContext, compute_hit, offensive_skill
from game.content_loader import BaseSkillDef, load_base_skills

# {skill_id: BaseSkillDef} и {base_class: [defs]} — для клавиатур/валидации
BASE_SKILLS_BY_CLASS: dict[str, list[BaseSkillDef]] = load_base_skills()
BASE_SKILL_DEFS: dict[str, BaseSkillDef] = {
    s.id: s for skills in BASE_SKILLS_BY_CLASS.values() for s in skills
}


def _make_handler(skill: BaseSkillDef):
    def handler(ctx: SkillContext) -> None:
        actor = ctx.actor
        actor.cooldowns[skill.id] = skill.cd  # тикнется в резолвере/дуэли
        target = ctx.resolve_target()

        # --- Урон ---
        if skill.effect == "double_hit":
            # два отдельных удара, крит считается для каждого независимо
            if target is not None:
                ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier))
                ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier))
        elif skill.multiplier > 0 and target is not None:
            force_crit = skill.effect == "guaranteed_crit"
            ctx.hits.append(
                compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, force_crit)
            )

        # --- Эффекты ---
        if skill.effect == "stun":
            if target is not None:
                # контроль срабатывает в ТОТ ЖЕ ход (resolver проверяет FREEZE
                # до действий целей); резист WIL — оба режима, DR — только PvP
                pvp = ctx.session.mode != CombatMode.PVE
                res = control.try_apply_control(
                    target, base_duration=1, source_id=actor.id, rng=ctx.rng, pvp=pvp
                )
                if res.immune:
                    ctx.lines.append(combat_flavor.control_blocked_line(ctx.rng))
                elif res.resisted:
                    ctx.lines.append(combat_flavor.control_resisted_line(ctx.rng))
                else:
                    ctx.lines.append(combat_flavor.control_line(ctx.rng))
                    if res.reduced:
                        ctx.lines.append(combat_flavor.control_reduced_line(ctx.rng))
                    if res.immunity_granted:
                        from game.combat import balance_config as bc
                        ctx.lines.append(
                            combat_flavor.control_immune_line(ctx.rng, bc.CC_IMMUNITY_DURATION)
                        )
        elif skill.effect == "self_damage_buff":
            actor.apply_effect(
                EffectKind.DAMAGE_BUFF, skill.effect_value, skill.effect_duration, actor.id
            )
        elif skill.effect == "self_dodge_buff":
            actor.apply_effect(
                EffectKind.DODGE, skill.effect_value, skill.effect_duration, actor.id
            )
        elif skill.effect == "target_vuln":
            if target is not None:
                target.apply_effect(
                    EffectKind.VULNERABILITY, skill.effect_value, skill.effect_duration, actor.id
                )

    return handler


# Регистрация всех базовых навыков как атакующих умений
for _skill in BASE_SKILL_DEFS.values():
    offensive_skill(_skill.id)(_make_handler(_skill))


def skills_for_class(base_class: str) -> list[BaseSkillDef]:
    return BASE_SKILLS_BY_CLASS.get(base_class, [])


# Навыки, накладывающие контроль (пропуск хода) — для порядка фаз в резолвере
CONTROL_SKILL_IDS: set[str] = {s.id for s in BASE_SKILL_DEFS.values() if s.effect == "stun"}


def is_control_skill(skill_id: str | None) -> bool:
    return skill_id in CONTROL_SKILL_IDS
