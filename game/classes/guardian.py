"""Страж (Guardian) — Воин, естественная роль: Танк (дотягивается до Саппорта).

Кит патча 39, ч.3 (content/skills/subclass_skills.json):
  - Удар щитом — урон + Провокация (PvE: форс цели мобов; PvP: дебаф урона
    противника по другим целям);
  - Глухая оборона — многоходовый блок (EffectKind.BLOCK_STANCE) + самолечение
    за срезанные удары (EffectKind.BLOCK_HEAL, резолвится в resolver.py);
    ТАКЖЕ сохраняет интеграцию с микробаффами активного пресета (патч 14, ч.3:
    full_block_chance/heal_on_block_pct_max_hp/counterstrike_mult) — это
    отдельная, всё ещё активная фича, не часть контента подкласса;
  - Каменная хватка — урон + оглушение, дженерик-навык (effect="stun" в JSON,
    регистрируется автоматически в game/combat/subclass_skills.py);
  - Несокрушимый — потолок входящего урона за удар (EffectKind.DAMAGE_CAP,
    резолвится в resolver.py).
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat.session import CombatMode, Effect, EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, defensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

GUARDIAN = register(
    SubclassDef(
        id="guardian",
        title="Страж",
        base_class="warrior",
        primary_stat="str",
        natural_role=Role.TANK,
        flexible_roles=(Role.SUPPORT,),
        skills=("attack", "guardian_shield_bash", "guardian_block", "guardian_stonegrip", "guardian_unbreakable"),
    )
)

_BLOCK = SUBCLASS_SKILL_DEFS["guardian_block"]
_UNBREAKABLE = SUBCLASS_SKILL_DEFS["guardian_unbreakable"]


@defensive_skill("guardian_shield_bash")
def shield_bash(ctx: SkillContext) -> None:
    """Удар щитом: 130% урона + Провокация на 2 хода (PvE — форс цели мобов,
    PvP — дебаф урона противника по остальным целям). ЗАЩИТНЫЙ навык (не
    зависит от фазы атаки моба — провокация должна успеть подействовать в
    этот же ход)."""
    skill = SUBCLASS_SKILL_DEFS["guardian_shield_bash"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is not None:
        ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True))

    enemies = ctx.session.alive_enemies_of(actor)
    if ctx.session.mode == CombatMode.PVE:
        for enemy in enemies:
            if enemy.kind == "mob":
                enemy.taunted_by = actor.id
        ctx.lines.append(f"{actor.name} провоцирует врагов — цели мобов форсированы!")
    else:
        for enemy in enemies:
            enemy.effects.append(
                Effect(
                    kind=EffectKind.PROVOKE_PVP,
                    value=bc.PROVOKE_PVP_DAMAGE_REDUCTION,
                    remaining_ticks=bc.PROVOKE_PVP_DURATION_TICKS,
                    source_id=actor.id,
                )
            )
        ctx.lines.append(f"{actor.name} провоцирует: урон противников по другим целям снижен")


@defensive_skill("guardian_block")
def block(ctx: SkillContext) -> None:
    """Глухая оборона: без урона, 2 хода снижения урона + самолечение за
    срезанные удары. Микробаффы активного пресета (патч 14, ч.3) добавляют:
    шанс ПОЛНОГО блока (Несокрушимость), самоисцеление при блоке (Живительный
    блок), контрудар (Возмездие) — читаются из buff_modifiers как и раньше."""
    actor = ctx.actor
    actor.cooldowns[_BLOCK.id] = _BLOCK.cd

    full_block_chance = actor.buff_modifiers.get("full_block_chance", 0.0)
    if full_block_chance > 0 and ctx.rng.random() < full_block_chance:
        actor.block_reduction = 1.0
        ctx.lines.append(f"{actor.name} блокирует удар ПОЛНОСТЬЮ 🛡✨")
    else:
        actor.apply_effect(EffectKind.BLOCK_STANCE, _BLOCK.effect_value, _BLOCK.effect_duration, actor.id)
        ctx.lines.append(f"{actor.name} уходит в глухую оборону 🛡")
    actor.apply_effect(EffectKind.BLOCK_HEAL, bc.GUARDIAN_BLOCK_HEAL_PCT, _BLOCK.effect_duration, actor.id)

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
                compute_hit(
                    actor, target, ctx.rng, label="контратакует",
                    multiplier=counterstrike_mult, is_ability=True,
                )
            )


@defensive_skill("guardian_unbreakable")
def unbreakable(ctx: SkillContext) -> None:
    """Несокрушимый: без урона, 3 хода потолок входящего урона за удар."""
    actor = ctx.actor
    actor.cooldowns[_UNBREAKABLE.id] = _UNBREAKABLE.cd
    actor.apply_effect(EffectKind.DAMAGE_CAP, _UNBREAKABLE.effect_value, _UNBREAKABLE.effect_duration, actor.id)
    ctx.lines.append(f"{actor.name} застывает несокрушимой глыбой")
