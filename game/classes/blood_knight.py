"""Кровавый рыцарь (Blood Knight) — Воин, ДД (сустейн-лайфстил).

Кит патча 39, ч.3: Кровопуск (частый лайфстил), Жатва (бонус-хил при низком
HP), Кровавая печать (метка цели — усиливает лайфстил ЛЮБОЙ последующей атаки
рыцаря по ней на 3 хода), Багровый пир (себестоимость HP, крупный бурст+хил).

Патч 44: срезано только лечение — 87% PvP-винрейт без единого проигрышного
матчапа. Сломало идентичность подкласса (сустейн-ДД перестал восстанавливаться).
Патч 45, ч.2: вектор нерфа сменён на урон (множители снижены до уровня Клинка
теней), лайфстил частично возвращён — кап BLOOD_KNIGHT_HEAL_CAP_PER_TURN
(единый на все 4 навыка лайфстила, патч 44) остаётся в силе.
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import CombatantState, EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

BLOOD_KNIGHT = register(
    SubclassDef(
        id="blood_knight",
        title="Кровавый рыцарь",
        base_class="warrior",
        primary_stat="str",
        natural_role=Role.DD,
        flexible_roles=(Role.TANK, Role.SUPPORT),
        skills=(
            "attack", "blood_knight_lifesteal_strike", "blood_knight_harvest",
            "blood_knight_blood_seal", "blood_knight_crimson_feast",
        ),
    )
)


def _most_injured_ally(ctx: SkillContext, actor: CombatantState) -> CombatantState | None:
    allies = ctx.session.alive_allies_of(actor)
    if not allies:
        return None
    return min(allies, key=lambda a: a.current_hp / a.max_hp if a.max_hp else 0.0)


def _lifesteal_heal(ctx: SkillContext, hit, ratio: float) -> None:
    """Лечение от лайфстила: усиливается BLOOD_KNIGHT_BLOOD_SEAL_MULT, если
    цель под Кровавой печатью этого рыцаря (EffectKind.BLOOD_SEAL), и всегда
    капается BLOOD_KNIGHT_HEAL_CAP_PER_TURN — единообразно для всех навыков
    лайфстила (патч 44: раньше кап применялся только к Кровопуску).

    Патч 47, ч.2 — микробаффы пула: «Жажда» (низкий HP), «Разрыв вен» (крит),
    «Ненасытность» (безусловно) добавляются к ratio ДО капа; «Вечный голод»
    поднимает сам кап; «Разделённая жажда» отдаёт долю итогового лечения
    самому раненому живому союзнику (нет-оп в бою 1×1 — союзников не бывает)."""
    actor = ctx.actor
    target = ctx.session.combatants.get(hit.target_id)
    if target is not None and target.effect_from(EffectKind.BLOOD_SEAL, actor.id) is not None:
        ratio *= bc.BLOOD_KNIGHT_BLOOD_SEAL_MULT
    if hit.crit:
        ratio += actor.buff_modifiers.get("crit_lifesteal_bonus", 0.0)
    if actor.current_hp < actor.max_hp * 0.5:
        ratio += actor.buff_modifiers.get("low_hp_lifesteal_bonus", 0.0)
    ratio += actor.buff_modifiers.get("lifesteal_ratio_bonus", 0.0)

    cap_pct = bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN + actor.buff_modifiers.get("heal_cap_bonus", 0.0)
    heal = round(hit.amount * ratio)
    heal = min(heal, round(actor.max_hp * cap_pct))
    heal = max(heal, 0)  # страховка (патч 45, ч.1) — лечение не может быть отрицательным
    if heal > 0:
        ctx.heals.append(
            PendingHeal(source_id=actor.id, target_id=actor.id, amount=heal, label="восполняет кровью")
        )
        shared_pct = actor.buff_modifiers.get("shared_heal_pct", 0.0)
        if shared_pct > 0:
            ally = _most_injured_ally(ctx, actor)
            if ally is not None:
                shared_heal = round(heal * shared_pct)
                if shared_heal > 0:
                    ctx.heals.append(
                        PendingHeal(
                            source_id=actor.id, target_id=ally.id, amount=shared_heal,
                            label="делится кровью",
                        )
                    )


@offensive_skill("blood_knight_lifesteal_strike")
def lifesteal_strike(ctx: SkillContext) -> None:
    """Кровопуск: 115% урона, лечит на 20% нанесённого (капается — самый
    частый навык кита, cd2)."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_lifesteal_strike"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    _lifesteal_heal(ctx, hit, skill.effect_value)


@offensive_skill("blood_knight_harvest")
def harvest(ctx: SkillContext) -> None:
    """Жатва: 150% урона. Если HP актёра ниже 50% — лечит на 30% нанесённого."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_harvest"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    if actor.current_hp < actor.max_hp * 0.5:
        _lifesteal_heal(ctx, hit, skill.effect_value)


@offensive_skill("blood_knight_blood_seal")
def blood_seal(ctx: SkillContext) -> None:
    """Кровавая печать: 85% урона, метит цель на 3 хода — все последующие
    атаки рыцаря по ней лечат в BLOOD_KNIGHT_BLOOD_SEAL_MULT раз сильнее."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_blood_seal"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))
    target.apply_effect(EffectKind.BLOOD_SEAL, 1.0, skill.effect_duration, actor.id)
    ctx.lines.append(f"{target.name} отмечен Кровавой печатью 🩸")


@offensive_skill("blood_knight_crimson_feast")
def crimson_feast(ctx: SkillContext) -> None:
    """Багровый пир: тратит 15% текущего HP, 200% урона, лечит на 45% нанесённого.

    Патч 47, ч.2: «Кровавый пакт» снижает себестоимость HP, «Пиршество»
    добавляет к ratio лечения — только у этого навыка (не у всех четырёх)."""
    skill = SUBCLASS_SKILL_DEFS["blood_knight_crimson_feast"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    cost_pct = bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST * (
        1.0 - actor.buff_modifiers.get("crimson_feast_cost_reduction", 0.0)
    )
    cost = round(actor.current_hp * cost_pct)
    actor.current_hp = max(actor.current_hp - cost, 1)
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    ratio = skill.effect_value + actor.buff_modifiers.get("crimson_feast_heal_bonus", 0.0)
    _lifesteal_heal(ctx, hit, ratio)
