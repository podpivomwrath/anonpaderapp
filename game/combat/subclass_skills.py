"""Навыки подклассов (патч 39, ч.3) — data-driven из content/skills/subclass_skills.json,
заменяют базовые навыки класса после выбора подкласса (30 ур).

effect=null/stun/target_vuln/self_dodge_buff регистрируются ЗДЕСЬ дженериком
(та же логика, что в base_skills.py). effect="custom" — бespoke хендлер,
зарегистрированный вручную в соответствующем game/classes/<subclass>.py при
импорте этого модуля (см. game/classes/__init__.py); дженерик такие id пропускает.
"""

from game.combat import combat_flavor, control
from game.combat.session import CombatMode, EffectKind
from game.combat.skills import SkillContext, compute_hit, offensive_skill
from game.content_loader import SubclassSkillDef, load_subclass_skills

SUBCLASS_SKILLS_BY_ID: dict[str, list[SubclassSkillDef]] = load_subclass_skills()
SUBCLASS_SKILL_DEFS: dict[str, SubclassSkillDef] = {
    s.id: s for skills in SUBCLASS_SKILLS_BY_ID.values() for s in skills
}

_GENERIC_EFFECTS = {None, "stun", "target_vuln", "self_dodge_buff"}


def _make_handler(skill: SubclassSkillDef):
    def handler(ctx: SkillContext) -> None:
        actor = ctx.actor
        actor.cooldowns[skill.id] = skill.cd
        target = ctx.resolve_target()

        if skill.multiplier > 0 and target is not None:
            ctx.hits.append(
                compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
            )

        if skill.effect == "stun":
            if target is not None:
                pvp = ctx.session.mode != CombatMode.PVE
                res = control.try_apply_control(
                    target, base_duration=1, source_id=actor.id, rng=ctx.rng, pvp=pvp
                )
                if pvp:
                    if res.immune:
                        ctx.lines.append(combat_flavor.pvp_control_blocked_line(target.name))
                    elif res.resisted:
                        ctx.lines.append(combat_flavor.pvp_control_resisted_line(target.name))
                    else:
                        ctx.lines.append(combat_flavor.pvp_control_line(target.name))
                        if res.reduced:
                            ctx.lines.append(combat_flavor.pvp_control_reduced_line(target.name))
                        if res.immunity_granted:
                            from game.combat import balance_config as bc
                            ctx.lines.append(
                                combat_flavor.pvp_control_immune_line(target.name, bc.CC_IMMUNITY_DURATION)
                            )
                elif res.immune:
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


for _skill in SUBCLASS_SKILL_DEFS.values():
    if _skill.effect in _GENERIC_EFFECTS:
        offensive_skill(_skill.id)(_make_handler(_skill))


def skills_for_subclass(subclass_id: str | None) -> list[SubclassSkillDef]:
    return SUBCLASS_SKILLS_BY_ID.get(subclass_id, [])


# Навыки, накладывающие контроль (пропуск хода) — для порядка фаз в резолвере.
# Дженерик-стан + вручную дополняется bespoke-модулями (напр. poisoner_disrupt —
# контроль с шансом, добавляется в game/classes/poisoner.py).
CONTROL_SKILL_IDS: set[str] = {s.id for s in SUBCLASS_SKILL_DEFS.values() if s.effect == "stun"}


def is_control_skill(skill_id: str | None) -> bool:
    return skill_id in CONTROL_SKILL_IDS
