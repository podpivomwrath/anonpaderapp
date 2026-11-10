"""Обработчики 10 навыков, которых не было ни у одного класса (руны-навыки,
2026-11-10). Данные - content/skills/rune_skills.json, ступени -
game/economy/ability_config.py. Регистрируются импортом из game/classes.
"""

from game import plural
from game.combat import ability_rules, control
from game.combat.session import CombatMode, EffectKind
from game.combat.skill_catalog import tuned
from game.combat.skills import (
    PendingHeal,
    SkillContext,
    compute_hit,
    defensive_skill,
    offensive_skill,
    set_cooldown,
)

#: «Прикрыть собой»: доля урона по прикрытому, что уходит прикрывающему.
COVER_SHARE = 0.3
#: «Прикрыть собой»: щит прикрытому - доля здоровья прикрывающего на единицу
#: силы навыка (0.3 -> 15% здоровья).
COVER_SHIELD_PER_VALUE = 0.5
#: «Сомкнуть ряды»: порог «кто-то из своих падает» и щит без этого условия.
CLOSE_RANKS_THRESHOLD = 0.3
CLOSE_RANKS_WEAK_SHIELD = 0.08


def _own(ctx: SkillContext) -> list:
    return [ctx.actor] + list(ctx.session.alive_allies_of(ctx.actor))


def _share(c) -> float:
    return c.current_hp / c.max_hp if c.max_hp else 1.0


def _effects_word(n: int) -> str:
    return plural.count(n, "эффект", "эффекта", "эффектов")


@defensive_skill("cleanse_water")
def cleanse_water(ctx: SkillContext) -> None:
    """Чистая вода: снимает плохие эффекты с самого пострадавшего своего и
    на effect_duration ходов защищает его от контроля."""
    skill = tuned(ctx, "cleanse_water")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    own = _own(ctx)
    afflicted = [c for c in own if any(e.kind in ability_rules.BAD for e in c.effects)]
    target = min(afflicted or own, key=_share)
    removed = ability_rules.cleanse(target, round(skill.effect_value))
    target.apply_effect(EffectKind.CONTROL_IMMUNE, 1.0, skill.effect_duration, actor.id)
    heal = actor.buff_modifiers.get("cleanse_heal", 0.0)
    if heal > 0:
        ctx.heals.append(PendingHeal(source_id=actor.id, target_id=target.id,
                                     amount=round(target.max_hp * heal), label="Чистая вода лечит"))
    if removed and actor.buff_modifiers.get("cleanse_reflect", 0.0) > 0:
        for effect in removed:
            source = ctx.session.combatants.get(effect.source_id)
            if source is not None and source.alive and source.side != actor.side:
                source.apply_effect(effect.kind, effect.value, max(effect.remaining_ticks, 1), actor.id)
    if removed:
        ctx.lines.append(f"💧 Чистая вода: с {target.name} снято {_effects_word(len(removed))}, "
                         "контроль ему пока не страшен")
    else:
        ctx.lines.append(f"💧 Чистая вода: {target.name} пока не поддаётся контролю")


@offensive_skill("bitter_wound")
def bitter_wound(ctx: SkillContext) -> None:
    """Горькая рана: удар, после которого цель хуже лечится и получает
    слабые щиты (EffectKind.HEAL_REDUCTION)."""
    skill = tuned(ctx, "bitter_wound")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    if hit.missed:
        return
    backlash = actor.buff_modifiers.get("bitter_backlash", 0.0)
    target.apply_effect(EffectKind.HEAL_REDUCTION, skill.effect_value, skill.effect_duration, actor.id,
                        tag=f"bitter:{backlash}" if backlash > 0 else None)
    ctx.lines.append(f"🩹 {target.name} получает горькую рану: лечение и щиты слабее")


@offensive_skill("shatter")
def shatter(ctx: SkillContext) -> None:
    """Раскол: разбивает щиты цели; если щит был, удар сильнее."""
    skill = tuned(ctx, "shatter")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    target = ctx.resolve_target()
    if target is None:
        return
    shields = [e for e in target.effects if e.kind == EffectKind.SHIELD_POOL and e.value > 0]
    broken = round(sum(e.value for e in shields))
    for effect in shields:
        target.effects.remove(effect)
    if actor.buff_modifiers.get("shatter_cap", 0.0) > 0:
        target.effects[:] = [e for e in target.effects if e.kind != EffectKind.DAMAGE_CAP]
    multiplier = skill.multiplier * (1 + skill.effect_value if broken else 1)
    ctx.hits.append(compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True))
    if broken:
        ctx.lines.append(f"💥 Раскол: щит {target.name} разбит")
        steal = actor.buff_modifiers.get("shatter_steal", 0.0)
        if steal > 0:
            actor.apply_effect(EffectKind.SHIELD_POOL, round(broken * steal), 2, actor.id, tag="step:shatter")


@offensive_skill("mute")
def mute(ctx: SkillContext) -> None:
    """Немота: удар, после которого цель не может применять навыки
    (EffectKind.SILENCE, сопротивление Воли и защита от цепочки контроля -
    как у заморозки). Мобы под немотой не применяют способности."""
    skill = tuned(ctx, "mute")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    if hit.missed or not target.alive:
        return
    pvp = ctx.session.mode != CombatMode.PVE
    res = control.try_apply_control(
        target, base_duration=max(skill.effect_duration, 1), source_id=actor.id, rng=ctx.rng, pvp=pvp,
        duration_bonus=ability_rules.ctrl_mobs_bonus(actor, skill.id, target),
        chance_bonus=actor.buff_modifiers.get(f"rune:grip@{skill.id}", 0.0)
        + ability_rules.mod(actor, "skill_ctrl_pierce", skill.id),
        kind=EffectKind.SILENCE,
    )
    if res.immune or res.resisted:
        ctx.lines.append(f"🤐 {target.name} не поддаётся Немоте")
        return
    ctx.lines.append(f"🤐 {target.name} онемел: навыки ему сейчас недоступны")
    if actor.buff_modifiers.get("mute_full_cd", 0.0) > 0:
        ability_rules.lock_declared_skill(ctx.session, target, ctx.lines, "Немота")


@defensive_skill("counter_strike")
def counter_strike(ctx: SkillContext) -> None:
    """Ответный удар: effect_duration ходов доля урона по бойцу
    возвращается ударившему (тот же механизм, что эликсир «Кровь за кровь»)."""
    skill = tuned(ctx, "counter_strike")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    actor.apply_effect(EffectKind.BLOOD_REFLECT, skill.effect_value, skill.effect_duration, actor.id)
    actor.reflect_label = "отвечает ударом"
    ctx.lines.append(f"🔁 {actor.name} ждёт удара, чтобы ответить")


@offensive_skill("strip_veil")
def strip_veil(ctx: SkillContext) -> None:
    """Сорвать покров: удар, сбивающий с цели полезные эффекты."""
    skill = tuned(ctx, "strip_veil")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier, is_ability=True)
    ctx.hits.append(hit)
    if hit.missed:
        return
    removed = ability_rules.strip(target, round(skill.effect_value))
    if removed:
        ctx.lines.append(f"🧹 С {target.name} сорвано {_effects_word(len(removed))}")


@defensive_skill("breather")
def breather(ctx: SkillContext) -> None:
    """Передышка: перезарядка остальных навыков бойца короче, лечение себя."""
    skill = tuned(ctx, "breather")
    actor = ctx.actor
    turns = 2 if actor.buff_modifiers.get("breather_turns", 0.0) > 0 else 1
    for sid in list(actor.cooldowns):
        if sid == skill.id:
            continue
        actor.cooldowns[sid] -= turns
        if actor.cooldowns[sid] <= 0:
            del actor.cooldowns[sid]
    if actor.buff_modifiers.get("breather_reset", 0.0) > 0 and actor.cooldowns:
        longest = max(actor.cooldowns, key=actor.cooldowns.get)
        if longest != skill.id:
            del actor.cooldowns[longest]
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    if turns == 1 and skill.effect_value > 0:
        ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id,
                                     amount=round(actor.max_hp * skill.effect_value), label="переводит дух"))
    ctx.lines.append(f"🌬 {actor.name} переводит дух: навыки готовы раньше")


@defensive_skill("cover_ally")
def cover_ally(ctx: SkillContext) -> None:
    """Прикрыть собой: щит самому раненому союзнику и перенос части урона по
    нему на себя (EffectKind.COVERED, resolver._cover_redirect). Без
    союзника - щит себе вполсилы."""
    skill = tuned(ctx, "cover_ally")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    shield = round(actor.max_hp * COVER_SHIELD_PER_VALUE * skill.effect_value)
    allies = sorted(ctx.session.alive_allies_of(actor), key=_share)
    count = 2 if actor.buff_modifiers.get("cover_two", 0.0) > 0 else 1
    covered = allies[:count]
    if not covered:
        actor.apply_effect(EffectKind.SHIELD_POOL, shield // 2, skill.effect_duration, actor.id, tag="step:cover_ally")
        ctx.lines.append(f"🛡 {actor.name} закрывается щитом")
        return
    for ally in covered:
        ally.apply_effect(EffectKind.SHIELD_POOL, shield, skill.effect_duration, actor.id, tag="step:cover_ally")
        ally.apply_effect(EffectKind.COVERED, COVER_SHARE, skill.effect_duration, actor.id)
    names = ", ".join(a.name for a in covered)
    ctx.lines.append(f"🛡 {actor.name} прикрывает собой: {names}")


def close_ranks_shields(ctx_or_session, actor, value: float, duration: int, lines: list[str]) -> None:
    """Щит «Сомкнуть ряды» всей своей стороне - и с кнопки, и самим
    срабатыванием (пробуждение)."""
    session = getattr(ctx_or_session, "session", ctx_or_session)
    own = [actor] + list(session.alive_allies_of(actor))
    threshold = CLOSE_RANKS_THRESHOLD + actor.buff_modifiers.get("close_ranks_threshold", 0.0)
    low = any(_share(c) < threshold for c in own)
    pct = value if low else CLOSE_RANKS_WEAK_SHIELD
    for c in own:
        c.apply_effect(EffectKind.SHIELD_POOL, round(c.max_hp * pct), duration, actor.id, tag="step:close_ranks")
    lines.append(f"🛡 {actor.name}: ряды сомкнуты, щит {round(pct * 100)}% здоровья каждому")


@defensive_skill("close_ranks")
def close_ranks(ctx: SkillContext) -> None:
    """Сомкнуть ряды: щит всей своей стороне, сильный - если кто-то из своих
    уже падает."""
    skill = tuned(ctx, "close_ranks")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    close_ranks_shields(ctx, actor, skill.effect_value, skill.effect_duration, ctx.lines)


def close_ranks_auto(session, lines: list[str]) -> None:
    """Пробуждение «Сомкнуть ряды»: раз за бой срабатывает само, когда кто-то
    из своих падает ниже порога. Зовёт резолвер после ударов хода."""
    for actor in session.combatants.values():
        if not actor.alive or actor.buff_modifiers.get("close_ranks_auto", 0.0) <= 0:
            continue
        if getattr(actor, "close_ranks_used", False):
            continue
        own = [actor] + list(session.alive_allies_of(actor))
        threshold = CLOSE_RANKS_THRESHOLD + actor.buff_modifiers.get("close_ranks_threshold", 0.0)
        if any(_share(c) < threshold for c in own):
            actor.close_ranks_used = True
            skill = tuned(actor, "close_ranks")
            close_ranks_shields(session, actor, skill.effect_value, skill.effect_duration, lines)


@offensive_skill("reckoning")
def reckoning(ctx: SkillContext) -> None:
    """Расплата: удар на долю урона, полученного бойцом за этот бой, но не
    сильнее трёх его обычных ударов. Счётчик после удара обнуляется
    (пробуждение - падает вдвое)."""
    skill = tuned(ctx, "reckoning")
    actor = ctx.actor
    set_cooldown(actor, skill.id, skill.cd, ctx.rng)
    target = ctx.resolve_target()
    if target is None:
        return
    hit = compute_hit(actor, target, ctx.rng, skill.name, 1.0, is_ability=True)
    taken = getattr(actor, "taken_total", 0)
    if actor.buff_modifiers.get("reckoning_shields", 0.0) > 0:
        taken += getattr(actor, "shield_taken_total", 0)
    if not hit.missed:
        cap = round(hit.amount * (3 + actor.buff_modifiers.get("reckoning_cap", 0.0)))
        hit.amount = max(min(round(taken * skill.effect_value), cap), 1)
    ctx.hits.append(hit)
    keep = actor.buff_modifiers.get("reckoning_keep", 0.0)
    actor.taken_total = round(getattr(actor, "taken_total", 0) * keep)
    actor.shield_taken_total = round(getattr(actor, "shield_taken_total", 0) * keep)
