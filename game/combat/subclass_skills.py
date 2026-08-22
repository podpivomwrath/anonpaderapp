"""Навыки подклассов (патч 39, ч.3) — data-driven из content/skills/subclass_skills.json,
заменяют базовые навыки класса после выбора подкласса (30 ур).

effect=null/stun/target_vuln/self_dodge_buff регистрируются ЗДЕСЬ дженериком
(та же логика, что в base_skills.py). effect="custom" — бespoke хендлер,
зарегистрированный вручную в соответствующем game/classes/<subclass>.py при
импорте этого модуля (см. game/classes/__init__.py); дженерик такие id пропускает.
"""

from game.combat import balance_config as bc
from game.combat import combat_flavor, control
from game.combat.session import CombatMode, EffectKind
from game.combat.skills import (
    ELEMENT_SKILL_TAGS,
    SkillContext,
    compute_hit,
    element_damage_multiplier,
    offensive_skill,
    register_element_use,
    set_cooldown,
)
from game.content_loader import SubclassSkillDef, load_subclass_skills

SUBCLASS_SKILLS_BY_ID: dict[str, list[SubclassSkillDef]] = load_subclass_skills()
SUBCLASS_SKILL_DEFS: dict[str, SubclassSkillDef] = {
    s.id: s for skills in SUBCLASS_SKILLS_BY_ID.values() for s in skills
}

_GENERIC_EFFECTS = {None, "stun", "target_vuln", "self_dodge_buff"}


def _make_handler(skill: SubclassSkillDef):
    def handler(ctx: SkillContext) -> None:
        actor = ctx.actor
        set_cooldown(actor, skill.id, skill.cd, ctx.rng)
        register_element_use(actor, skill.id)
        target = ctx.resolve_target()

        if skill.multiplier > 0 and target is not None:
            # Патч 49, ч.2: элементальный бонус урона (Ледяная мощь/Всеобщая
            # стихия) — для generic-навыков это только Ледяные оковы (elementalist_ice).
            element = ELEMENT_SKILL_TAGS.get(skill.id)
            multiplier = skill.multiplier * element_damage_multiplier(actor, element)
            ctx.hits.append(
                compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True)
            )

        if skill.effect == "stun":
            if target is not None:
                pvp = ctx.session.mode != CombatMode.PVE
                # Патч 47: Элементалист — «Оцепенение» (+ход к заморозке),
                # «Глубокая заморозка» (+шанс). 0 у всех остальных подклассов.
                duration_bonus = int(actor.buff_modifiers.get("freeze_duration_bonus", 0))
                chance_bonus = actor.buff_modifiers.get("control_chance_bonus", 0.0)
                res = control.try_apply_control(
                    target, base_duration=bc.CONTROL_BASE_DURATION_TICKS, source_id=actor.id, rng=ctx.rng, pvp=pvp,
                    duration_bonus=duration_bonus, chance_bonus=chance_bonus,
                )
                # Патч 49: «Ледяное поле» — заморозка основной цели слегка чилит
                # соседних (только при нескольких противниках — иначе нет-оп).
                # Интерпретация неоднозначной формулировки "снижение скорости
                # накопления стаков" — у Элементалиста нет своей системы стаков,
                # поэтому применяем к сопротивлению контролю (тот же дебафф-
                # эффект, что и «Тепловой шок»), а не изобретаем новую систему.
                ice_field_bonus = actor.buff_modifiers.get("ice_field_chill_pct", 0.0)
                if res.applied and ice_field_bonus > 0:
                    others = [e for e in ctx.session.alive_enemies_of(actor) if e.id != target.id]
                    for other in others:
                        other.apply_effect(EffectKind.CONTROL_RESIST_DOWN, ice_field_bonus, 1, actor.id)
                # Единый краткий текст независимо от режима (патч 43, ч.1).
                if res.immune:
                    ctx.lines.append(combat_flavor.control_blocked_line(target.name))
                elif res.resisted:
                    ctx.lines.append(combat_flavor.control_resisted_line(target.name))
                else:
                    # Патч 52, баг 1: «теряет ход» больше НЕ печатается здесь —
                    # единственное место теперь резолвер (game/combat/resolver.py,
                    # фаза 4a/4b) — см. комментарий в base_skills.py.
                    if res.reduced:
                        ctx.lines.append(combat_flavor.control_reduced_line(target.name))
                    if res.immunity_granted:
                        ctx.lines.append(
                            combat_flavor.control_immune_line(target.name, bc.CC_IMMUNITY_DURATION)
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
