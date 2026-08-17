"""Сухие механические описания микробаффов для вкладки «Испытания» (патч 48).

Каждое описание — функция, читающая ЖИВЫЕ значения из game.combat.
balance_config / content/buffs.json (stat_modifiers), а не захардкоженный
текст с продублированными числами — иначе описание разойдётся с реальностью
при следующей калибровке (см. tests/test_calibration.py — там же проверяется,
что buffs.json совпадает с константами balance_config).

Только для баффов с implemented=true в контенте (см. content/buffs.json).
Для остальных — вкладка показывает "в разработке" и не рендерит эту функцию.
"""

from game.combat import balance_config as bc
from game.content_loader import BuffDef


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _pp(value: float) -> str:
    """Проценты-пункты (лайфстил/кап и т.п. — складываются с базовым % напрямую)."""
    return f"{round(value * 100)}pp"


def _turns(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        word = "ход"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "хода"
    else:
        word = "ходов"
    return f"{n} {word}"


def _describe_guardian_bulwark(b: BuffDef) -> str:
    return f"Шанс полностью заблокировать входящий удар: {_pct(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE)}."


def _describe_guardian_unyielding(b: BuffDef) -> str:
    return (
        f"+{_turns(bc.GUARDIAN_UNYIELDING_PROVOKE_BONUS_TURNS)} к длительности Провокации "
        f"от Удара щитом (база: {_turns(bc.PROVOKE_PVP_DURATION_TICKS)})."
    )


def _describe_guardian_vital_block(b: BuffDef) -> str:
    return f"Лечит на {_pct(bc.GUARDIAN_HEAL_ON_BLOCK)} от максимального HP при успешном блоке."


def _describe_guardian_retribution(b: BuffDef) -> str:
    return f"Контрудар при блоке наносит {_pct(bc.GUARDIAN_COUNTERSTRIKE_MULT)} от обычного удара."


def _describe_guardian_heavy_hand(b: BuffDef) -> str:
    return f"+{_pct(bc.GUARDIAN_HEAVY_HAND_BONUS)} урона всеми навыками."


def _describe_blood_knight_blood_rage(b: BuffDef) -> str:
    return f"+{_pct(bc.BLOOD_KNIGHT_RAGE_DAMAGE_BONUS)} урона всеми навыками."


def _describe_blood_knight_thirst(b: BuffDef) -> str:
    return f"+{_pp(bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS)} к лайфстилу, если HP ниже 50%."


def _describe_blood_knight_vein_rupture(b: BuffDef) -> str:
    return f"+{_pp(bc.BLOOD_KNIGHT_VEIN_RUPTURE_CRIT_LIFESTEAL_BONUS)} к лайфстилу при критическом ударе."


def _describe_blood_knight_recklessness(b: BuffDef) -> str:
    return f"+{_pct(bc.BLOOD_KNIGHT_RECKLESSNESS_DAMAGE_BONUS)} урона всеми навыками."


def _describe_blood_knight_insatiable(b: BuffDef) -> str:
    return f"+{_pp(bc.BLOOD_KNIGHT_INSATIABLE_LIFESTEAL_BONUS)} к лайфстилу всех навыков лайфстила, безусловно."


def _describe_blood_knight_eternal_hunger(b: BuffDef) -> str:
    total = bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN + bc.BLOOD_KNIGHT_ETERNAL_HUNGER_HEAL_CAP_BONUS
    return (
        f"+{_pp(bc.BLOOD_KNIGHT_ETERNAL_HUNGER_HEAL_CAP_BONUS)} к капу лечения за ход "
        f"(итого {_pct(total)} от maxHP вместо {_pct(bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)})."
    )


def _describe_blood_knight_second_wind(b: BuffDef) -> str:
    return (
        f"-{_pct(bc.BLOOD_KNIGHT_SECOND_WIND_DAMAGE_REDUCTION)} входящего урона, "
        f"если HP ниже {_pct(bc.BLOOD_KNIGHT_SECOND_WIND_HP_THRESHOLD)}."
    )


def _describe_blood_knight_blood_armor(b: BuffDef) -> str:
    return f"-{_pct(bc.BLOOD_KNIGHT_BLOOD_ARMOR_DAMAGE_REDUCTION)} входящего урона, безусловно."


def _describe_blood_knight_pain_resistant(b: BuffDef) -> str:
    return f"-{_pct(bc.BLOOD_KNIGHT_PAIN_RESISTANT_CRIT_REDUCTION)} урона от критических ударов по себе."


def _describe_blood_knight_feast(b: BuffDef) -> str:
    return f"Багровый пир лечит на дополнительные {_pp(bc.BLOOD_KNIGHT_FEAST_CRIMSON_HEAL_BONUS)} нанесённого урона."


def _describe_blood_knight_shared_thirst(b: BuffDef) -> str:
    return (
        f"{_pct(bc.BLOOD_KNIGHT_SHARED_THIRST_ALLY_HEAL_PCT)} лечения от лайфстила достаётся "
        f"самому раненому живому союзнику. Не действует в бою 1×1 — союзников нет."
    )


def _describe_blood_knight_blood_pact(b: BuffDef) -> str:
    reduced = bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST * (1.0 - bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION)
    return (
        f"-{_pct(bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION)} себестоимости HP Багрового пира "
        f"(было {_pct(bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)} текущего HP, станет {_pct(reduced)})."
    )


def _describe_blood_knight_shared_feast(b: BuffDef) -> str:
    return f"+{_pct(bc.BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS)} урона всеми навыками."


def _describe_poisoner_lingering_poison(b: BuffDef) -> str:
    return (
        f"+{_turns(bc.POISONER_LINGERING_POISON_BONUS_TURNS)} к длительности яда от Отравленного "
        f"клинка (база: {_turns(bc.POISONER_POISON_DURATION_TICKS)})."
    )


def _describe_elementalist_deep_freeze(b: BuffDef) -> str:
    return f"+{_pct(bc.ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS)} к шансу наложить оглушение/заморозку Ледяными оковами."


def _describe_elementalist_numbness(b: BuffDef) -> str:
    return f"+{_turns(bc.ELEMENTALIST_NUMBNESS_FREEZE_BONUS_TURNS)} к длительности заморозки от Ледяных оков."


def _describe_elementalist_thrift(b: BuffDef) -> str:
    return f"Шанс {_pct(bc.ELEMENTALIST_ECONOMY_NO_COOLDOWN_CHANCE)}, что применённый навык не уходит на перезарядку."


def _describe_elementalist_overload(b: BuffDef) -> str:
    return f"Раз в {_turns(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS)} следующий применённый навык не уходит на перезарядку."


def _describe_elementalist_elemental_flow(b: BuffDef) -> str:
    return f"3 разных стихийных умения подряд усиливают следующее действие на +{_pct(bc.ELEMENTALIST_ELEMENTAL_FLOW_BONUS)}."


_GENERATORS = {
    "guardian_bulwark": _describe_guardian_bulwark,
    "guardian_unyielding": _describe_guardian_unyielding,
    "guardian_vital_block": _describe_guardian_vital_block,
    "guardian_retribution": _describe_guardian_retribution,
    "guardian_heavy_hand": _describe_guardian_heavy_hand,
    "blood_knight_blood_rage": _describe_blood_knight_blood_rage,
    "blood_knight_thirst": _describe_blood_knight_thirst,
    "blood_knight_vein_rupture": _describe_blood_knight_vein_rupture,
    "blood_knight_recklessness": _describe_blood_knight_recklessness,
    "blood_knight_insatiable": _describe_blood_knight_insatiable,
    "blood_knight_eternal_hunger": _describe_blood_knight_eternal_hunger,
    "blood_knight_second_wind": _describe_blood_knight_second_wind,
    "blood_knight_blood_armor": _describe_blood_knight_blood_armor,
    "blood_knight_pain_resistant": _describe_blood_knight_pain_resistant,
    "blood_knight_feast": _describe_blood_knight_feast,
    "blood_knight_shared_thirst": _describe_blood_knight_shared_thirst,
    "blood_knight_blood_pact": _describe_blood_knight_blood_pact,
    "blood_knight_shared_feast": _describe_blood_knight_shared_feast,
    "poisoner_lingering_poison": _describe_poisoner_lingering_poison,
    "elementalist_deep_freeze": _describe_elementalist_deep_freeze,
    "elementalist_numbness": _describe_elementalist_numbness,
    "elementalist_thrift": _describe_elementalist_thrift,
    "elementalist_overload": _describe_elementalist_overload,
    "elementalist_elemental_flow": _describe_elementalist_elemental_flow,
}

CATEGORY_LABELS = {
    "damage": "Урон",
    "defense": "Оборона",
    "control_utility": "Контроль/утилита",
    "group_support": "Групповая поддержка",
}


def describe(buff: BuffDef) -> str:
    """Сухое механическое описание; пустая строка для нереализованных
    (implemented=false — за них отвечает только пометка "в разработке")."""
    if not buff.implemented:
        return ""
    generator = _GENERATORS.get(buff.id)
    return generator(buff) if generator is not None else ""


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)
