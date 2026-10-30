"""Применение эффектов боевых эликсиров (патч 16).

Боевые эликсиры — "бесплатное действие": накладываются МИМО объявления хода,
мутируют CombatantState напрямую (см. bot/handlers/combat.py). Вызывающий уже
обязан проверить лимит за бой / заморозку / наличие в инвентаре ДО вызова —
эта функция только накладывает эффект и возвращает строку для чата.
"""

from game.combat.session import SCROLL_WARD_TAG, SECOND_HEART_TAG, CombatantState, EffectKind
from game.economy import elixir_config as ec


def _recovered(target: CombatantState, amount: int) -> int:
    from game.combat import shared_rules

    return shared_rules.recovered(target, amount)


def drink_heal(actor: CombatantState, elixir_id: str) -> str:
    """Лечебное зелье - тоже бесплатное действие (2026-10-14, решение
    владельца): лечит сразу, ход не тратится. Раньше шло действием хода."""
    from game.combat.session import white_max_hp

    amount = ec.heal_amount(elixir_id, white_max_hp(actor)) or 0
    amount = _recovered(actor, round(amount * (1 + actor.buff_modifiers.get("rune:clean_still", 0.0))))  # руна
    before = actor.current_hp
    actor.current_hp = min(actor.max_hp, before + amount)
    healed = actor.current_hp - before
    if healed <= 0:
        return "🧪 Зелье выпито, но ты и так цел."
    return f"🧪 Зелье лечит: +{healed} HP ({actor.current_hp}/{actor.max_hp})."


def heal_seen(actor: CombatantState, name: str, healed: int) -> str:
    """Строка для остальных бойцов: союзник выпил лечебное (2026-10-30, владелец)."""
    if healed <= 0:
        return f"🧪 {name} пьёт лечебное зелье, но здоровье и так полное."
    return f"🧪 {name} пьёт лечебное зелье: +{healed} HP ({actor.current_hp}/{actor.max_hp})."


def elixir_seen(name: str, elixir) -> str:
    """Строка для остальных бойцов: кто-то выпил боевой эликсир (баг 243,
    2026-10-30: в PvP не было видно, что соперник пьёт)."""
    return f"{elixir.emoji} {name} пьёт «{elixir.name}»."


def _apply_scroll(actor: CombatantState, elixir_id: str, combatants) -> str:
    """Свитки (2026-10-13): на всю сторону бойца или на всех врагов. Без
    списка бойцов (вызов из старого кода) - только на себя."""
    everyone = list((combatants or {actor.id: actor}).values())
    allies = [c for c in everyone if c.alive and c.side == actor.side]
    enemies = [c for c in everyone if c.alive and c.side != actor.side]
    if elixir_id == "scroll_healing":
        healed = []
        for c in allies:
            before = c.current_hp
            c.current_hp = min(c.max_hp, c.current_hp + _recovered(c, round(c.max_hp * ec.SCROLL_HEAL_PCT)))
            if c.current_hp > before:
                healed.append(f"{c.name} +{c.current_hp - before}")
        tail = ", ".join(healed) if healed else "все и так целы"
        return f"📜 Свиток лечения вспыхивает - раны затягиваются ({tail})."
    if elixir_id == "scroll_ward":
        for c in allies:
            c.apply_effect(
                EffectKind.SHIELD_POOL, float(round(c.max_hp * ec.SCROLL_WARD_PCT)),
                ec.SCROLL_WARD_DURATION, actor.id, tag=SCROLL_WARD_TAG,
            )
        names = ", ".join(c.name for c in allies)
        return f"📜 Свиток оберега укрывает щитом на {ec.SCROLL_WARD_DURATION} хода: {names}."
    if elixir_id == "scroll_vulnerability":
        for c in enemies:
            c.apply_effect(
                EffectKind.VULNERABILITY, ec.SCROLL_VULNERABILITY, ec.SCROLL_VULNERABILITY_DURATION, actor.id,
            )
        pct = round(ec.SCROLL_VULNERABILITY * 100)
        return f"📜 Свиток уязвимости: {ec.SCROLL_VULNERABILITY_DURATION} хода враги получают на {pct}% больше урона."
    return "Свиток рассыпается пеплом."


def apply_combat_elixir(actor: CombatantState, elixir_id: str, combatants=None) -> str:
    """combatants - все бойцы боя (id -> боец): нужны свиткам. Руна «Чистая
    перегонка» (2026-10-31) усиливает величину эффекта своего эликсира;
    эффекты «да/нет» и свитки - без изменений."""
    boost = actor.buff_modifiers.get("rune:clean_still", 0.0)
    if not boost or elixir_id.startswith("scroll_"):
        return _apply_elixir(actor, elixir_id, combatants)
    before = {id(e): e.value for e in actor.effects}
    text = _apply_elixir(actor, elixir_id, combatants)
    for e in actor.effects:
        if e.source_id != actor.id or e.kind in _BINARY_KINDS:
            continue
        old = before.get(id(e), 0.0)
        if e.value > old:
            e.value = old + (e.value - old) * (1 + boost)
    return text


def _apply_elixir(actor: CombatantState, elixir_id: str, combatants=None) -> str:
    if elixir_id.startswith("scroll_"):
        return _apply_scroll(actor, elixir_id, combatants)
    if elixir_id == "ashen_fever":
        actor.apply_effect(
            EffectKind.ASHEN_FEVER, ec.ASHEN_FEVER_DAMAGE_BONUS_STEP,
            ec.ASHEN_FEVER_DURATION, actor.id,
        )
        return "🔥 Кровь вскипает пеплом. Удары станут злее - но жгут и тебя самого."

    if elixir_id == "last_breath":
        actor.apply_effect(EffectKind.LAST_BREATH, 1.0, ec.LAST_BREATH_DURATION, actor.id)
        return (
            f"💀 Дыхание задерживается на самой грани. Смерть подождёт - один раз, "
            f"{ec.LAST_BREATH_DURATION} хода."
        )

    if elixir_id == "blood_for_blood":
        actor.apply_effect(
            EffectKind.BLOOD_REFLECT, ec.BLOOD_FOR_BLOOD_REFLECT_PCT,
            ec.BLOOD_FOR_BLOOD_DURATION, actor.id,
        )
        return "🩸 Кровь готова ответить на кровь."

    if elixir_id == "blood_clarity":
        actor.apply_effect(EffectKind.CONTROL_IMMUNE, 1.0, ec.BLOOD_CLARITY_DURATION, actor.id)
        return "🧿 Разум проясняется - оковам не за что зацепиться."

    if elixir_id == "second_heart":
        shield_amount = round(actor.max_hp * ec.SECOND_HEART_SHIELD_PCT_MAX_HP)
        actor.apply_effect(
            EffectKind.SHIELD_POOL, float(shield_amount), ec.SECOND_HEART_DURATION, actor.id,
            tag=SECOND_HEART_TAG,
        )
        shield_amount = round(sum(
            e.value for e in actor.effects_of(EffectKind.SHIELD_POOL) if getattr(e, "tag", None) == SECOND_HEART_TAG
        ))
        return f"🛡️ Второе сердце укрывает тебя щитом ({shield_amount} поглощения)."

    if elixir_id == "ashen_haze":
        # Эликсир пьётся ДО хода, поэтому эффект для резолвера уже «старый»
        # и тикает в первый же ход. Прежние -1 к длительности давали морок на
        # 1 ход вместо обещанных 2 (2026-10-12, жалоба игрока).
        actor.apply_effect(
            EffectKind.DODGE, ec.ASHEN_HAZE_DODGE_CHANCE, ec.ASHEN_HAZE_DURATION, actor.id,
        )
        return "🌫️ Морок укрывает тебя пеплом - удары будут находить лишь его."

    if elixir_id == "shard_blood":
        bonus = round(actor.level * ec.SHARD_BLOOD_DAMAGE_PER_LEVEL)
        actor.apply_effect(
            EffectKind.FLAT_DAMAGE_BONUS, float(bonus), ec.SHARD_BLOOD_DURATION, actor.id
        )
        return f"⚡ Осколки въедаются в клинок - каждый удар несёт +{bonus} урона."

    return "Эликсир не оказывает эффекта."


#: Эффекты «да/нет» (спасение, иммунитет): у склянки на группу слабеет не
#: сила, а срок - вдвое, но не меньше хода.
_BINARY_KINDS = (EffectKind.LAST_BREATH, EffectKind.CONTROL_IMMUNE)


def throw_flask(actor: CombatantState, elixir_id: str, combatants, power: float) -> str:
    """Метательная склянка (2026-10-23): зелье на всю свою сторону, но
    слабее - power от силы (лечение, величина эффекта; у эффектов «да/нет» -
    срок). Свитки сюда не идут: они и так на всех."""
    from game.combat.session import white_max_hp

    allies = [c for c in (combatants or {actor.id: actor}).values() if c.alive and c.side == actor.side]
    flask = _flask_name(elixir_id)
    if ec.heal_amount(elixir_id, white_max_hp(actor)) is not None:
        healed = []
        for c in allies:
            amount = _recovered(c, round((ec.heal_amount(elixir_id, white_max_hp(c)) or 0) * power))
            before = c.current_hp
            c.current_hp = min(c.max_hp, before + amount)
            if c.current_hp > before:
                healed.append(f"{c.name} +{c.current_hp - before}")
        return f"🧴 {flask} разбивается над своими: " + (", ".join(healed) if healed else "все и так целы") + "."
    for c in allies:
        # Уже действующий свой эффект склянка не трогает (2026-10-23): раньше
        # она перезаписывала его - выпитый в полную силу освежался и
        # продлевался, хотя метнули слабее.
        before = [(e, e.value, e.remaining_ticks, e.power) for e in c.effects]
        apply_combat_elixir(c, elixir_id, combatants)
        for e, value, ticks, power_was in before:
            e.value, e.remaining_ticks, e.power = value, ticks, power_was
        for effect in c.effects:
            if any(effect is e for e, *_ in before):
                continue
            if effect.kind in _BINARY_KINDS:
                effect.remaining_ticks = max(1, round(effect.remaining_ticks * power))
            else:
                effect.value = effect.value * power
                effect.power = power
    names = ", ".join(c.name for c in allies)
    return f"🧴 {flask} разбивается над своими ({names}): на каждого слабее, чем выпить самому."


def _flask_name(elixir_id: str) -> str:
    """Склянка с названием зелья (баг 173, 2026-10-30): раньше в логе было
    не понять, что именно разбилось."""
    from game.content_loader import load_elixirs

    edef = load_elixirs().get(elixir_id)
    return f"Склянка «{edef.name}»" if edef else "Склянка"
