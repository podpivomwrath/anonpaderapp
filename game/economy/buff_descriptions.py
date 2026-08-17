"""Сухие механические описания микробаффов для вкладки «Испытания» (патчи 48-49).

Каждое описание — функция, читающая ЖИВЫЕ значения из game.combat.
balance_config / content/skills (эффекты навыков) / content/buffs.json
(stat_modifiers), а не захардкоженный текст с продублированными числами —
иначе описание разойдётся с реальностью при следующей калибровке (см.
tests/test_calibration.py — там же проверяется, что buffs.json совпадает с
константами balance_config).

Патч 49, ч.1 — правило формулировок: показывать ИТОГОВОЕ значение, а не
арифметику прибавки, и никогда не использовать сокращения "pp"/"пп"/"%%".
Если итоговое значение зависит от статов цели (напр. шанс контроля — от её
WIL) и не может быть посчитано заранее — прибавка пишется словами
("на N процентных пунктов"), без сокращений.

Только для баффов с implemented=true в контенте (см. content/buffs.json).
Для остальных — вкладка показывает "в разработке" и не рендерит эту функцию.
"""

from game.combat import balance_config as bc
from game.content_loader import BuffDef


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _points(value: float) -> str:
    """Прибавка, для которой нет единого "было/стало" (несколько базовых
    значений сразу, или зависит от статов цели) — пишется словами целиком,
    без сокращений pp/пп."""
    return f"{round(value * 100)} процентных пунктов"


def _turns(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        word = "ход"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "хода"
    else:
        word = "ходов"
    return f"{n} {word}"


def _crimson_feast_base_ratio() -> float:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["blood_knight_crimson_feast"].effect_value


def _describe_guardian_bulwark(b: BuffDef) -> str:
    return f"Шанс полностью заблокировать входящий удар: {_pct(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE)}."


def _describe_guardian_unyielding(b: BuffDef) -> str:
    base = bc.PROVOKE_PVP_DURATION_TICKS
    total = base + bc.GUARDIAN_UNYIELDING_PROVOKE_BONUS_TURNS
    return f"Провокация от Удара щитом длится {_turns(total)} вместо {_turns(base)}."


def _describe_guardian_vital_block(b: BuffDef) -> str:
    return f"Лечит на {_pct(bc.GUARDIAN_HEAL_ON_BLOCK)} от максимального HP при успешном блоке."


def _describe_guardian_retribution(b: BuffDef) -> str:
    return f"Контрудар при блоке наносит {_pct(bc.GUARDIAN_COUNTERSTRIKE_MULT)} от обычного удара."


def _describe_guardian_heavy_hand(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.GUARDIAN_HEAVY_HAND_BONUS)}."


def _describe_blood_knight_blood_rage(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.BLOOD_KNIGHT_RAGE_DAMAGE_BONUS)}."


def _describe_blood_knight_thirst(b: BuffDef) -> str:
    return (
        f"Лайфстил всех навыков лайфстила увеличен на {_points(bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS)}, "
        f"если здоровье ниже 50%."
    )


def _describe_blood_knight_vein_rupture(b: BuffDef) -> str:
    return f"Лайфстил увеличен на {_points(bc.BLOOD_KNIGHT_VEIN_RUPTURE_CRIT_LIFESTEAL_BONUS)} при критическом ударе."


def _describe_blood_knight_recklessness(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.BLOOD_KNIGHT_RECKLESSNESS_DAMAGE_BONUS)}."


def _describe_blood_knight_insatiable(b: BuffDef) -> str:
    return f"Лайфстил всех навыков лайфстила увеличен на {_points(bc.BLOOD_KNIGHT_INSATIABLE_LIFESTEAL_BONUS)}, безусловно."


def _describe_blood_knight_eternal_hunger(b: BuffDef) -> str:
    total = bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN + bc.BLOOD_KNIGHT_ETERNAL_HUNGER_HEAL_CAP_BONUS
    return f"Кап лечения за ход — {_pct(total)} от maxHP вместо {_pct(bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)}."


def _describe_blood_knight_second_wind(b: BuffDef) -> str:
    return (
        f"Входящий урон снижен на {_pct(bc.BLOOD_KNIGHT_SECOND_WIND_DAMAGE_REDUCTION)}, "
        f"если здоровье ниже {_pct(bc.BLOOD_KNIGHT_SECOND_WIND_HP_THRESHOLD)}."
    )


def _describe_blood_knight_blood_armor(b: BuffDef) -> str:
    return f"Входящий урон снижен на {_pct(bc.BLOOD_KNIGHT_BLOOD_ARMOR_DAMAGE_REDUCTION)}, безусловно."


def _describe_blood_knight_pain_resistant(b: BuffDef) -> str:
    return f"Урон от критических ударов по себе снижен на {_pct(bc.BLOOD_KNIGHT_PAIN_RESISTANT_CRIT_REDUCTION)}."


def _describe_blood_knight_feast(b: BuffDef) -> str:
    base = _crimson_feast_base_ratio()
    total = base + bc.BLOOD_KNIGHT_FEAST_CRIMSON_HEAL_BONUS
    return f"Багровый пир лечит на {_pct(total)} нанесённого урона вместо {_pct(base)}."


def _describe_blood_knight_shared_thirst(b: BuffDef) -> str:
    return (
        f"{_pct(bc.BLOOD_KNIGHT_SHARED_THIRST_ALLY_HEAL_PCT)} лечения от лайфстила достаётся "
        f"самому раненому живому союзнику. Не действует в бою 1×1 — союзников нет."
    )


def _describe_blood_knight_blood_pact(b: BuffDef) -> str:
    base = bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST
    reduced = base * (1.0 - bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION)
    return f"Себестоимость HP Багрового пира — {_pct(reduced)} текущего HP вместо {_pct(base)}."


def _describe_blood_knight_shared_feast(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS)}."


def _describe_poisoner_lingering_poison(b: BuffDef) -> str:
    base = bc.POISONER_POISON_DURATION_TICKS
    total = base + bc.POISONER_LINGERING_POISON_BONUS_TURNS
    return f"Яд от Отравленного клинка держится {_turns(total)} вместо {_turns(base)}."


def _describe_elementalist_deep_freeze(b: BuffDef) -> str:
    # Итоговый шанс зависит от WIL цели (control_resist) — заранее не считается.
    return f"Шанс наложить оглушение/заморозку Ледяными оковами увеличен на {_points(bc.ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS)}."


def _describe_elementalist_numbness(b: BuffDef) -> str:
    base = bc.CONTROL_BASE_DURATION_TICKS
    total = base + bc.ELEMENTALIST_NUMBNESS_FREEZE_BONUS_TURNS
    return f"Заморозка от Ледяных оков длится {_turns(total)} вместо {_turns(base)}."


def _describe_elementalist_thrift(b: BuffDef) -> str:
    return f"Шанс {_pct(bc.ELEMENTALIST_ECONOMY_NO_COOLDOWN_CHANCE)}, что применённый навык не уходит на перезарядку."


def _describe_elementalist_overload(b: BuffDef) -> str:
    return f"Раз в {_turns(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS)} следующий применённый навык не уходит на перезарядку."


def _describe_elementalist_elemental_flow(b: BuffDef) -> str:
    return f"3 разных стихийных умения подряд усиливают следующее действие на {_pct(bc.ELEMENTALIST_ELEMENTAL_FLOW_BONUS)}."


def _describe_elementalist_flame_power(b: BuffDef) -> str:
    return (
        f"Урон Огненной плети увеличен на {_pct(bc.ELEMENTALIST_FLAME_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке — берётся больший бонус."
    )


def _describe_elementalist_frost_power(b: BuffDef) -> str:
    return (
        f"Урон Ледяных оков увеличен на {_pct(bc.ELEMENTALIST_FROST_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке — берётся больший бонус."
    )


def _describe_elementalist_storm_power(b: BuffDef) -> str:
    return (
        f"Урон Цепи молний увеличен на {_pct(bc.ELEMENTALIST_STORM_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке — берётся больший бонус."
    )


def _describe_elementalist_universal_element(b: BuffDef) -> str:
    return (
        f"Урон всех стихийных навыков увеличен на {_pct(bc.ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS)}. "
        f"Не складывается с Пламенной/Ледяной мощью или Мощью бури на одном навыке — берётся больший бонус."
    )


def _describe_elementalist_heat_shock(b: BuffDef) -> str:
    return (
        f"В момент, когда Горение спадает с цели, её сопротивление контролю снижается на "
        f"{_points(bc.ELEMENTALIST_HEAT_SHOCK_RESIST_DOWN)} на 1 ход."
    )


def _describe_elementalist_chain_lightning(b: BuffDef) -> str:
    base = 2
    total = base + bc.ELEMENTALIST_CHAIN_LIGHTNING_EXTRA_TARGETS
    return f"Цепь молний поражает {total} доп. цели вместо {base}."


def _describe_elementalist_firestorm(b: BuffDef) -> str:
    return (
        f"Горение от Огненной плети распространяется на других живых противников с "
        f"{_pct(bc.ELEMENTALIST_FIRESTORM_SPREAD_PCT)} силы. "
        f"Действует только в бою с несколькими противниками (массовый PvP) — в одиночном бою эффекта нет."
    )


def _describe_elementalist_ice_field(b: BuffDef) -> str:
    return (
        f"При заморозке основной цели Ледяными оковами сопротивление контролю других живых противников "
        f"снижается на {_points(bc.ELEMENTALIST_ICE_FIELD_CHILL_PCT)} на 1 ход. "
        f"Действует только в бою с несколькими противниками (массовый PvP) — в одиночном бою эффекта нет."
    )


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
    "elementalist_flame_power": _describe_elementalist_flame_power,
    "elementalist_frost_power": _describe_elementalist_frost_power,
    "elementalist_storm_power": _describe_elementalist_storm_power,
    "elementalist_universal_element": _describe_elementalist_universal_element,
    "elementalist_heat_shock": _describe_elementalist_heat_shock,
    "elementalist_chain_lightning": _describe_elementalist_chain_lightning,
    "elementalist_firestorm": _describe_elementalist_firestorm,
    "elementalist_ice_field": _describe_elementalist_ice_field,
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
