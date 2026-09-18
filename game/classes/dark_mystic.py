"""Тёмный мистик — Маг, ЕДИНСТВЕННЫЙ хилер (осознанное решение дизайна:
престижная роль топового рейд-контента). Дотягивается до ДД и лёгкого Танка.

Кит патча 39, ч.3: Кровавый пакт — прямой урон, часть конвертируется в
исцеление; Оберег — щит (EffectKind.SHIELD_POOL, остаток превращается в
лечение при истечении — уже существующая логика resolver.py, патч 16);
Иссушение — урон+хил, усилен по контролируемой цели; Круг тьмы — себестоимость
HP, массовое исцеление союзников (вне группы лечит себя вдвое сильнее).
"""

from game.classes.base import Role, SubclassDef, register
from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import EffectKind
from game.combat.skills import PendingHeal, SkillContext, compute_hit, offensive_skill
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

DARK_MYSTIC = register(
    SubclassDef(
        id="dark_mystic",
        title="Тёмный мистик",
        base_class="mage",
        primary_stat="int",
        natural_role=Role.HEALER,
        flexible_roles=(Role.DD, Role.TANK),
        skills=(
            "attack", "dark_mystic_blood_pact", "dark_mystic_ward",
            "dark_mystic_drain", "dark_mystic_circle",
        ),
    )
)


def _lowest_hp_ally_or_self(ctx: SkillContext):
    allies = ctx.session.alive_allies_of(ctx.actor)
    return min(allies, key=lambda c: c.current_hp / c.max_hp) if allies else ctx.actor


def _allies_by_hp(ctx: SkillContext) -> list:
    """Живые союзники по возрастанию доли HP: «Разделённому пакту» нужен
    ВТОРОЙ по тяжести раненый, «Кругу тьмы» - все сразу."""
    return sorted(ctx.session.alive_allies_of(ctx.actor), key=lambda c: c.current_hp / c.max_hp)


def _pay_hp(actor, pct: float, *, from_max: bool = False) -> int:
    """Плата собственным HP с учётом «Пакта крови+» (дешевле на долю).

    from_max=True берёт долю от МАКСИМУМА здоровья. Доля от текущего дешевеет
    вместе с самим здоровьем, и на низком HP плата превращается в формальность:
    «Самоотречение» на 20% здоровья стоило 2% максимума и давало постоянную
    прибавку - такой размен выгоден всегда, то есть выбором не является."""
    base = actor.max_hp if from_max else actor.current_hp
    reduction = actor.buff_modifiers.get("hp_cost_reduction", 0.0)
    cost = round(base * pct * (1.0 - reduction))
    actor.current_hp = max(actor.current_hp - cost, 1)
    return cost


def _solo_heal_penalty(ctx: SkillContext) -> float:
    """Вне группы лечение мистика слабее: он командный хилер, и его сила
    обязана расти от числа союзников, а не работать как личный сустейн."""
    return 1.0 if ctx.session.alive_allies_of(ctx.actor) else bc.DARK_MYSTIC_SOLO_HEAL_PENALTY


def _edge_multiplier(actor) -> float:
    """«Грань»: урон и лечение сильнее, пока мистик сам на низком HP."""
    bonus = actor.buff_modifiers.get("edge_bonus", 0.0)
    if bonus <= 0:
        return 1.0
    return 1.0 + bonus if actor.current_hp < actor.max_hp * bc.DARK_MYSTIC_EDGE_HP_THRESHOLD else 1.0


@offensive_skill("dark_mystic_blood_pact")
def blood_pact(ctx: SkillContext) -> None:
    """Кровавый пакт: 110% урона цели, 70% нанесённого — лечением союзнику с
    наименьшим HP (себе, если союзника нет)."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_blood_pact"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    # Патч 56: «Самоотречение» доплачивает своим HP ради усиления пакта,
    # «Грань» усиливает урон и лечение на низком HP, «Тёмное вознаграждение»
    # срабатывает, если предыдущий навык уже стоил мистику крови.
    effect_mult = _edge_multiplier(actor)
    # Платит, только пока здоровья хватает: иначе пассивный бафф отдаёт долю
    # максимума на КАЖДОМ касте пакта и убивает мистика вернее противника.
    self_denial = (
        actor.buff_modifiers.get("self_denial", 0.0) > 0
        and actor.current_hp > actor.max_hp * bc.DARK_MYSTIC_SELF_DENIAL_MIN_HP
    )
    if self_denial:
        _pay_hp(actor, bc.DARK_MYSTIC_SELF_DENIAL_EXTRA_HP, from_max=True)
        effect_mult *= 1.0 + bc.DARK_MYSTIC_SELF_DENIAL_BONUS
    if actor.dark_reward_ready:
        effect_mult *= 1.0 + actor.buff_modifiers.get("dark_reward_bonus", 0.0)
        actor.dark_reward_ready = False

    hit = compute_hit(actor, target, ctx.rng, skill.name, skill.multiplier * effect_mult, is_ability=True)
    ctx.hits.append(hit)

    heal_target = _lowest_hp_ally_or_self(ctx)
    # «Кровавая связь» и «Тёмный резонанс» поднимают долю урона, уходящую в лечение.
    conversion = skill.effect_value + actor.buff_modifiers.get("pact_conversion_bonus", 0.0)
    resonance = actor.buff_modifiers.get("resonance_bonus", 0.0)
    if resonance > 0 and heal_target.current_hp < heal_target.max_hp * bc.DARK_MYSTIC_RESONANCE_HP_THRESHOLD:
        conversion += resonance
    heal = max(round(hit.amount * conversion * _solo_heal_penalty(ctx)), 1)
    ctx.heals.append(PendingHeal(source_id=actor.id, target_id=heal_target.id, amount=heal, label="исцеляет тьмой"))

    ranked = _allies_by_hp(ctx)
    # «Разделённый пакт»: доля лечения уходит ВТОРОМУ по тяжести раненому.
    shared = actor.buff_modifiers.get("shared_pact_pct", 0.0)
    if shared > 0 and len(ranked) >= 2:
        ctx.heals.append(
            PendingHeal(source_id=actor.id, target_id=ranked[1].id,
                        amount=max(round(heal * shared), 1), label="делит пакт")
        )
    # «Круг тьмы» (бафф): раз в N ходов пакт лечит вдобавок всех союзников.
    interval = int(actor.buff_modifiers.get("circle_interval", 0))
    if interval and ranked and ctx.session.tick_number % interval == 0:
        share = actor.buff_modifiers.get("circle_pct", bc.DARK_MYSTIC_CIRCLE_PCT)
        for ally in ranked:
            ctx.heals.append(
                PendingHeal(source_id=actor.id, target_id=ally.id,
                            amount=max(round(heal * share), 1), label="исцеляет кругом тьмы")
            )

    # Пакт с «Самоотречением» тоже стоил собственного HP - заряжаем награду
    # уже ПОСЛЕ применения, чтобы этот же удар себя не усилил.
    if self_denial and actor.buff_modifiers.get("dark_reward_bonus", 0.0) > 0:
        actor.dark_reward_ready = True


@offensive_skill("dark_mystic_ward")
def ward(ctx: SkillContext) -> None:
    """Оберег: без урона, щит себе или союзнику (масштаб от Воли), 3 хода,
    остаток по истечении превращается в лечение (resolver.py, как «Второе
    сердце» — патч 16)."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_ward"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    # Патч 56: «Оберег крови» и «Стойкий оберег» увеличивают поглощение,
    # второй платит за это лишним ходом перезарядки. «Передача оберега»
    # разрешает накрывать союзника полной величиной.
    ward_target = _lowest_hp_ally_or_self(ctx)
    steadfast = actor.buff_modifiers.get("ward_absorb_bonus", 0.0)
    bonus = actor.buff_modifiers.get("ward_shield_bonus", 0.0) + steadfast
    absorb = round(
        actor.max_hp
        * formulas.support_power(actor.stats.will)
        * bc.DARK_MYSTIC_WARD_SHIELD_COEF
        * (1.0 + bonus)
    )
    if steadfast > 0:
        actor.cooldowns[skill.id] = skill.cd + bc.DARK_MYSTIC_STEADFAST_WARD_CD
    ward_target.apply_effect(EffectKind.SHIELD_POOL, absorb, skill.effect_duration, actor.id)
    ctx.lines.append(f"{actor.name} накрывает {ward_target.name} Оберегом (+{absorb} поглощения)")

    # «Передача оберега»: тем же навыком накрывается и самый израненный союзник,
    # полной величиной. Нужны живые союзники, иначе накрывать некого.
    transfer = actor.buff_modifiers.get("ward_transfer", 0.0)
    if transfer > 0:
        extra = next((c for c in _allies_by_hp(ctx) if c.id != ward_target.id), None)
        if extra is not None:
            extra.apply_effect(EffectKind.SHIELD_POOL, absorb, skill.effect_duration, actor.id)
            ctx.lines.append(f"{actor.name} передаёт Оберег: {extra.name} (+{absorb} поглощения)")


@offensive_skill("dark_mystic_drain")
def drain(ctx: SkillContext) -> None:
    """Иссушение: 160% урона, лечит на 50% нанесённого. Цель под контролем — урон +40%."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_drain"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    target = ctx.resolve_target()
    if target is None:
        return
    # По холоду бьёт сильнее: цель либо ещё под контролем, либо только что
    # оттуда вышла. Проверять один FREEZE мало - он гаснет в тот же ход, и
    # в последовательном бою очередь мистика наступает уже после.
    controlled = target.has_effect(EffectKind.FREEZE) or target.has_effect(EffectKind.CHILLED)
    multiplier = skill.multiplier * bc.DARK_MYSTIC_DRAIN_CONTROLLED_MULT if controlled else skill.multiplier
    hit = compute_hit(actor, target, ctx.rng, skill.name, multiplier, is_ability=True)
    ctx.hits.append(hit)
    heal = max(round(hit.amount * skill.effect_value * _solo_heal_penalty(ctx)), 1)
    ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id, amount=heal, label="исцеляется иссушением"))


@offensive_skill("dark_mystic_circle")
def circle_of_dark(ctx: SkillContext) -> None:
    """Круг тьмы: тратит 20% текущего HP, лечит всех союзников с силой, зависящей от Воли
    поддержки. Вне группы лечит себя вдвое сильнее."""
    skill = SUBCLASS_SKILL_DEFS["dark_mystic_circle"]
    actor = ctx.actor
    actor.cooldowns[skill.id] = skill.cd
    _pay_hp(actor, bc.DARK_MYSTIC_CIRCLE_HP_COST)
    # Патч 56: навык потратил собственное HP - «Тёмное вознаграждение» усилит
    # следующий Кровавый пакт.
    if actor.buff_modifiers.get("dark_reward_bonus", 0.0) > 0:
        actor.dark_reward_ready = True

    # support_power(WIL) - ДОЛЯ, а не плоское число (см. formulas.py), поэтому
    # и щит Оберега, и Круг тьмы считаются от максимума здоровья мистика.
    power = (
        actor.max_hp * formulas.support_power(actor.stats.will)
        * skill.effect_value * _edge_multiplier(actor)
    )
    allies = ctx.session.alive_allies_of(actor)
    if allies:
        for ally in allies:
            ctx.heals.append(PendingHeal(source_id=actor.id, target_id=ally.id, amount=round(power), label="исцеляет кругом тьмы"))
    else:
        ctx.heals.append(PendingHeal(source_id=actor.id, target_id=actor.id, amount=round(power * bc.DARK_MYSTIC_CIRCLE_SOLO_MULT), label="исцеляет кругом тьмы"))
