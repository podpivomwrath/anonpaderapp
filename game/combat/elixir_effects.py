"""Применение эффектов боевых эликсиров (патч 16).

Боевые эликсиры — "бесплатное действие": накладываются МИМО объявления хода,
мутируют CombatantState напрямую (см. bot/handlers/combat.py). Вызывающий уже
обязан проверить лимит за бой / заморозку / наличие в инвентаре ДО вызова —
эта функция только накладывает эффект и возвращает строку для чата.
"""

from game.combat.session import CombatantState, EffectKind
from game.economy import elixir_config as ec


def apply_combat_elixir(actor: CombatantState, elixir_id: str) -> str:
    if elixir_id == "ashen_fever":
        actor.apply_effect(
            EffectKind.ASHEN_FEVER, ec.ASHEN_FEVER_DAMAGE_BONUS_STEP,
            ec.ASHEN_FEVER_DURATION, actor.id,
        )
        return "🔥 Кровь вскипает пеплом. Удары станут злее — но жгут и тебя самого."

    if elixir_id == "last_breath":
        actor.apply_effect(EffectKind.LAST_BREATH, 1.0, ec.LAST_BREATH_DURATION, actor.id)
        return "💀 Дыхание задерживается на самой грани. Смерть подождёт — один раз."

    if elixir_id == "blood_for_blood":
        actor.apply_effect(
            EffectKind.BLOOD_REFLECT, ec.BLOOD_FOR_BLOOD_REFLECT_PCT,
            ec.BLOOD_FOR_BLOOD_DURATION, actor.id,
        )
        return "🩸 Кровь готова ответить на кровь."

    if elixir_id == "blood_clarity":
        actor.apply_effect(EffectKind.CONTROL_IMMUNE, 1.0, ec.BLOOD_CLARITY_DURATION, actor.id)
        return "🧿 Разум проясняется — оковам не за что зацепиться."

    if elixir_id == "second_heart":
        shield_amount = round(actor.max_hp * ec.SECOND_HEART_SHIELD_PCT_MAX_HP)
        actor.apply_effect(
            EffectKind.SHIELD_POOL, float(shield_amount), ec.SECOND_HEART_DURATION, actor.id
        )
        return f"🛡️ Второе сердце укрывает тебя щитом ({shield_amount} поглощения)."

    if elixir_id == "ashen_haze":
        # DODGE — обычная (не мгновенная) семантика тика в резолвере; -1 к
        # длительности компенсирует применение как "бесплатного действия"
        # (см. game/combat/resolver.py::_IMMEDIATE_EFFECT_KINDS).
        actor.apply_effect(
            EffectKind.DODGE, ec.ASHEN_HAZE_DODGE_CHANCE,
            max(ec.ASHEN_HAZE_DURATION - 1, 1), actor.id,
        )
        return "🌫️ Морок укрывает тебя пеплом — удары будут находить лишь его."

    if elixir_id == "shard_blood":
        bonus = round(actor.level * ec.SHARD_BLOOD_DAMAGE_PER_LEVEL)
        actor.apply_effect(
            EffectKind.FLAT_DAMAGE_BONUS, float(bonus), ec.SHARD_BLOOD_DURATION, actor.id
        )
        return f"⚡ Осколки въедаются в клинок — каждый удар несёт +{bonus} урона."

    return "Эликсир не оказывает эффекта."
