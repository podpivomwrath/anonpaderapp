"""Общие эффекты ступеней рун-навыков (2026-11-10).

Ключи "<вид>:<id навыка>" кладёт game/economy/ability_config.combat_modifiers.
Здесь - те, что срабатывают после навыка (after_skill, зовёт
shared_rules.run_skill), при добивании (on_kill) и при перезарядке
(skip_cooldown). Урон по условиям (skill_execute, skill_fresh,
skill_vs_ctrl, skill_desperate) и крит (skill_crit) - в game/combat/skills.py,
числа навыка (skill_bonus, skill_cd, skill_duration, skill_value) -
skill_catalog.tuned.

Строки в лог - короткие, со значком 🟣: так игрок видит, что сработала
ступень, а не случайность.
"""

from game.combat.session import EffectKind

#: Плохие эффекты - их снимает «Чистая вода» и ступени очищения.
BAD = (EffectKind.WEAKEN, EffectKind.VULNERABILITY, EffectKind.DOT, EffectKind.FREEZE, EffectKind.CHILLED,
       EffectKind.CONTROL_RESIST_DOWN, EffectKind.HEAL_REDUCTION, EffectKind.SILENCE)
#: Полезные эффекты - их сбивают «Сорвать покров» и ступени.
GOOD = (EffectKind.DAMAGE_BUFF, EffectKind.DODGE, EffectKind.SHIELD_POOL, EffectKind.BLOCK_STANCE,
        EffectKind.DAMAGE_CAP, EffectKind.CONTROL_IMMUNE, EffectKind.FLAT_DAMAGE_BONUS, EffectKind.BLOOD_REFLECT,
        EffectKind.ELEMENTAL_FLOW)

#: Сколько ходов держатся уязвимость, ослабление, «хуже лечится» от ступеней.
STEP_EFFECT_TURNS = 2


def mod(actor, kind: str, skill_id: str) -> float:
    return (getattr(actor, "buff_modifiers", None) or {}).get(f"{kind}:{skill_id}", 0.0)


def cleanse(target, count: int) -> list:
    """Снять с цели до count плохих эффектов (первыми - контроль). Вернёт снятые."""
    bad = sorted((e for e in target.effects if e.kind in BAD),
                 key=lambda e: e.kind not in (EffectKind.FREEZE, EffectKind.SILENCE))
    removed = bad[:max(count, 0)]
    for effect in removed:
        target.effects.remove(effect)
    return removed


def strip(target, count: int) -> list:
    """Сбить с цели до count полезных эффектов (первыми - щиты)."""
    good = sorted((e for e in target.effects if e.kind in GOOD),
                  key=lambda e: e.kind != EffectKind.SHIELD_POOL)
    removed = good[:max(count, 0)]
    for effect in removed:
        target.effects.remove(effect)
    return removed


def _skill_name(skill_id: str) -> str:
    from game.combat import skill_catalog

    skill = skill_catalog.skill_def(skill_id)
    return skill.name if skill else skill_id


def after_skill(actor, skill_id: str | None, ctx, hits_from: int) -> None:
    """Ступени навыка, что срабатывают после него: по целям этого навыка и на себя."""
    if not skill_id:
        return
    mods = actor.buff_modifiers or {}
    if not any(key.endswith(f":{skill_id}") for key in mods):
        return
    from game.combat import control
    from game.combat.session import CombatMode
    from game.combat.skills import PendingHeal, compute_hit

    session, rng, lines = ctx.session, ctx.rng, ctx.lines
    name = _skill_name(skill_id)
    hit_ids = []
    for h in ctx.hits[hits_from:]:
        if h.source_id == actor.id and not getattr(h, "missed", False) and h.target_id not in hit_ids:
            hit_ids.append(h.target_id)
    targets = [session.combatants[t] for t in hit_ids if t in session.combatants and t != actor.id]
    pvp = session.mode != CombatMode.PVE

    vuln = mod(actor, "skill_vuln", skill_id)
    weaken = mod(actor, "skill_weaken", skill_id)
    antiheal = mod(actor, "skill_antiheal", skill_id)
    stun = mod(actor, "skill_stun", skill_id)
    break_shield = mod(actor, "skill_break_shield", skill_id)
    strip_n = round(mod(actor, "skill_strip", skill_id))
    for target in targets:
        if vuln:
            target.apply_effect(EffectKind.VULNERABILITY, vuln, STEP_EFFECT_TURNS, actor.id)
        if weaken:
            target.apply_effect(EffectKind.WEAKEN, weaken, STEP_EFFECT_TURNS, actor.id)
        if antiheal:
            target.apply_effect(EffectKind.HEAL_REDUCTION, antiheal, STEP_EFFECT_TURNS, actor.id)
        if break_shield and any(e.kind == EffectKind.SHIELD_POOL for e in target.effects):
            target.effects[:] = [e for e in target.effects if e.kind != EffectKind.SHIELD_POOL]
            lines.append(f"🟣 «{name}» разбивает щит: {target.name}")
        if strip_n and strip(target, strip_n):
            lines.append(f"🟣 «{name}» сбивает с {target.name} защиту и усиления")
        if stun and target.alive and rng.random() < stun:
            res = control.try_apply_control(
                target, base_duration=1, source_id=actor.id, rng=rng, pvp=pvp,
                duration_bonus=ctrl_mobs_bonus(actor, skill_id, target),
                chance_bonus=mod(actor, "skill_ctrl_pierce", skill_id))
            if not (res.immune or res.resisted):
                lines.append(f"🟣 «{name}» оглушает: {target.name}")

    splash = mod(actor, "skill_splash", skill_id)
    if splash and hit_ids:
        others = [c for c in session.alive_enemies_of(actor) if c.id not in hit_ids]
        if others:
            ctx.hits.append(compute_hit(actor, rng.choice(others), rng, label="задевает", multiplier=splash,
                                        is_ability=True))

    shield = mod(actor, "skill_shield", skill_id)
    if shield and actor.max_hp > 0:
        actor.apply_effect(EffectKind.SHIELD_POOL, round(actor.max_hp * shield), STEP_EFFECT_TURNS, actor.id,
                           tag=f"step:{skill_id}")
    heal = mod(actor, "skill_heal", skill_id)
    if heal and actor.max_hp > 0:
        ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id,
                                     amount=round(actor.max_hp * heal), label=f"«{name}» лечит"))
    dodge = mod(actor, "skill_dodge", skill_id)
    if dodge:
        actor.apply_effect(EffectKind.DODGE, dodge, 1, actor.id)
    immune = round(mod(actor, "skill_ctrl_immune", skill_id))
    if immune:
        cleanse_control(actor)
        actor.apply_effect(EffectKind.CONTROL_IMMUNE, 1.0, immune, actor.id)
    cleanse_n = round(mod(actor, "skill_cleanse", skill_id))
    if cleanse_n:
        own = [actor] + list(session.alive_allies_of(actor))
        if cleanse_n >= 9:  # «по одному с каждого своего»
            done = sum(1 for c in own if cleanse(c, 1))
        else:
            weakest = min(own, key=lambda c: c.current_hp / c.max_hp if c.max_hp else 1.0)
            done = len(cleanse(weakest, cleanse_n))
        if done:
            lines.append(f"🟣 «{name}» снимает плохие эффекты")


def cleanse_control(target) -> None:
    target.effects[:] = [e for e in target.effects if e.kind not in (EffectKind.FREEZE, EffectKind.SILENCE)]


def ctrl_mobs_bonus(actor, skill_id: str, target) -> int:
    """Ступень «мобов держит на ход дольше» - только против мобов."""
    if getattr(target, "kind", None) != "mob":
        return 0
    return round(mod(actor, "skill_ctrl_mobs", skill_id))


def twice_chance(actor, skill_id: str) -> float:
    return mod(actor, "skill_twice", skill_id)


def reset_kill_chance(actor, skill_id: str) -> float:
    return mod(actor, "skill_reset_kill", skill_id)


def heal_on_kill(actor, skill_id: str) -> float:
    return mod(actor, "skill_heal_kill", skill_id)


def lifesteal(actor, skill_id: str | None) -> float:
    return mod(actor, "skill_lifesteal", skill_id) if skill_id else 0.0


def skip_cooldown(actor, skill_id: str) -> bool:
    """Ступень «пока у вас меньше 30% здоровья, навык без перезарядки»."""
    if not mod(actor, "skill_nocd_low", skill_id):
        return False
    return actor.max_hp > 0 and actor.current_hp < actor.max_hp * 0.3


def shield_power(actor) -> float:
    """Пассивка Стража: щиты от его навыков крепче."""
    return (getattr(actor, "buff_modifiers", None) or {}).get("shield_power", 0.0)


def ally_heal_power(actor) -> float:
    """Пассивка Тёмного мистика: лечение и щиты на союзников сильнее."""
    return (getattr(actor, "buff_modifiers", None) or {}).get("ally_heal_power", 0.0)
