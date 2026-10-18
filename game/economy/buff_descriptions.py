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
    """Прибавка к шансу, у которого нет одного «было» (зависит от статов):
    «+12% к шансу» - прибавляется к тому, что уже есть (20% станет 32%)."""
    return f"{round(value * 100)}%"


def _turns(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        word = "ход"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "хода"
    else:
        word = "ходов"
    return f"{n} {word}"


#: Правило текстов (2026-10-15, просьба владельца): понятно самому
#: неопытному игроку. Без жаргона («стак», «митигация», «пп», «PvE»): «заряд»,
#: «бой с мобами», «союзник» - и всегда, что именно и когда срабатывает.
_ALLIES_ONLY = "Работает только в бою вместе с союзниками (группа, рейд, разлом), в одиночку ничего не даёт."
_MANY_ENEMIES = "Работает только в бою против нескольких противников, против одного ничего не даёт."


def _crimson_feast_base_ratio() -> float:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["blood_knight_crimson_feast"].effect_value


def _describe_guardian_bulwark(b: BuffDef) -> str:
    return (
        f"Когда применяешь Глухую оборону, с шансом {_pct(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE)} в этот ход "
        "ты полностью блокируешь весь урон по себе (полный блок)."
    )


def _describe_guardian_unyielding(b: BuffDef) -> str:
    base = bc.PROVOKE_PVP_DURATION_TICKS
    total = base + bc.GUARDIAN_UNYIELDING_PROVOKE_BONUS_TURNS
    return f"Провокация от Удара щитом держится {_turns(total)} вместо {base}."


def _describe_guardian_vital_block(b: BuffDef) -> str:
    return (
        f"Каждый раз, когда применяешь Глухую оборону, восстанавливаешь {_pct(bc.GUARDIAN_HEAL_ON_BLOCK)} "
        "своего максимального здоровья."
    )


def _describe_guardian_heavy_hand(b: BuffDef) -> str:
    return f"Весь твой урон (обычная атака и навыки) больше на {_pct(bc.GUARDIAN_HEAVY_HAND_BONUS)}."


# --- Страж, микробаффы патча 56 ---


def _describe_guardian_sturdy_armor(b: BuffDef) -> str:
    return f"Весь урон по тебе меньше на {_pct(bc.GUARDIAN_STURDY_ARMOR_REDUCTION)}."


def _describe_guardian_reflection(b: BuffDef) -> str:
    return (
        f"Пока ты в Глухой обороне, {_pct(bc.GUARDIAN_REFLECTION_PCT)} урона, который она с тебя срезала, "
        "получает тот, кто ударил."
    )


def _describe_guardian_resilience(b: BuffDef) -> str:
    return (
        f"Пока у тебя меньше {_pct(bc.GUARDIAN_RESILIENCE_HP_THRESHOLD)} здоровья, урон по тебе "
        f"меньше ещё на {_pct(bc.GUARDIAN_RESILIENCE_REDUCTION)}."
    )


def _describe_guardian_command(b: BuffDef) -> str:
    return (
        f"Мобы бьют тебя на {_pct(bc.GUARDIAN_COMMAND_AGGRO_BONUS)} чаще, чем твоих союзников, - "
        "так ты прикрываешь группу. Против игроков не работает."
    )


def _describe_guardian_provoker_mark(b: BuffDef) -> str:
    total = bc.PROVOKE_PVP_DAMAGE_REDUCTION + bc.GUARDIAN_PROVOKER_MARK_BONUS
    return (
        f"В бою с игроками: пока действует твоя Провокация, противник, который бьёт не тебя, "
        f"наносит на {_pct(total)} меньше урона (без этого баффа - на {_pct(bc.PROVOKE_PVP_DAMAGE_REDUCTION)})."
    )


def _describe_guardian_guard(b: BuffDef) -> str:
    total = bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE + bc.GUARDIAN_GUARD_BLOCK_BONUS
    return (
        f"Шанс полного блока в Глухой обороне +{_pct(bc.GUARDIAN_GUARD_BLOCK_BONUS)}: вместе с Несокрушимостью "
        f"{_pct(total)} вместо {_pct(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE)}, без неё - {_pct(bc.GUARDIAN_GUARD_BLOCK_BONUS)}."
    )


def _describe_guardian_allys_shield(b: BuffDef) -> str:
    return (
        f"Когда ты в Глухой обороне, союзник с самым низким здоровьем тоже получает её защиту - "
        f"{_pct(bc.GUARDIAN_ALLYS_SHIELD_SHARE)} от твоей. {_ALLIES_ONLY}"
    )


def _describe_guardian_wall(b: BuffDef) -> str:
    return (
        "Глухая оборона снимает один плохой эффект (яд, ослабление и т.п.) с союзника, у которого "
        f"меньше всего здоровья. {_ALLIES_ONLY}"
    )


def _describe_guardian_counterattack(b: BuffDef) -> str:
    return (
        "Когда Глухая оборона срабатывает полным блоком, ты сразу бьёшь случайного врага: "
        f"{_pct(bc.GUARDIAN_COUNTERATTACK_MULT)} от твоей обычной атаки."
    )


def _describe_guardian_retribution(b: BuffDef) -> str:
    return (
        f"Чем больше урона срезала твоя Глухая оборона за последние {_turns(bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS)}, "
        f"тем сильнее ты бьёшь: за каждые срезанные 10% твоего максимального здоровья урон "
        f"+{_pct(bc.GUARDIAN_RETRIBUTION_PER_10PCT)}, но не больше +{_pct(bc.GUARDIAN_RETRIBUTION_CAP)}."
    )


def _describe_blood_knight_blood_rage(b: BuffDef) -> str:
    return f"Весь твой урон (обычная атака и навыки) больше на {_pct(bc.BLOOD_KNIGHT_RAGE_DAMAGE_BONUS)}."


def _describe_blood_knight_thirst(b: BuffDef) -> str:
    return (
        f"Пока у тебя меньше 50% здоровья, навыки, которые лечат тебя от нанесённого урона, лечат "
        f"больше: к их доле прибавляется {_points(bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS)} "
        "(например, было 20% от урона - станет 28%)."
    )


def _describe_blood_knight_vein_rupture(b: BuffDef) -> str:
    return (
        f"Если удар критический, лечение от нанесённого урона больше: к доле прибавляется "
        f"{_points(bc.BLOOD_KNIGHT_VEIN_RUPTURE_CRIT_LIFESTEAL_BONUS)} (было 20% от урона - станет 28%)."
    )


def _describe_blood_knight_recklessness(b: BuffDef) -> str:
    return f"Весь твой урон (обычная атака и навыки) больше на {_pct(bc.BLOOD_KNIGHT_RECKLESSNESS_DAMAGE_BONUS)}."


def _describe_blood_knight_insatiable(b: BuffDef) -> str:
    return (
        f"Навыки, которые лечат тебя от нанесённого урона, всегда лечат больше: к доле прибавляется "
        f"{_points(bc.BLOOD_KNIGHT_INSATIABLE_LIFESTEAL_BONUS)} (было 20% от урона - станет 25%)."
    )


def _describe_blood_knight_eternal_hunger(b: BuffDef) -> str:
    total = bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN + bc.BLOOD_KNIGHT_ETERNAL_HUNGER_HEAL_CAP_BONUS
    return (
        f"За один ход лечение от урона может вернуть тебе до {_pct(total)} максимального здоровья "
        f"вместо {_pct(bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)}."
    )


def _describe_blood_knight_second_wind(b: BuffDef) -> str:
    return (
        f"Пока у тебя меньше {_pct(bc.BLOOD_KNIGHT_SECOND_WIND_HP_THRESHOLD)} здоровья, урон по тебе "
        f"меньше на {_pct(bc.BLOOD_KNIGHT_SECOND_WIND_DAMAGE_REDUCTION)}."
    )


def _describe_blood_knight_blood_armor(b: BuffDef) -> str:
    return f"Весь урон по тебе меньше на {_pct(bc.BLOOD_KNIGHT_BLOOD_ARMOR_DAMAGE_REDUCTION)}, всегда."


def _describe_blood_knight_pain_resistant(b: BuffDef) -> str:
    return f"Критические удары по тебе наносят на {_pct(bc.BLOOD_KNIGHT_PAIN_RESISTANT_CRIT_REDUCTION)} меньше урона."


def _describe_blood_knight_feast(b: BuffDef) -> str:
    base = _crimson_feast_base_ratio()
    total = base + bc.BLOOD_KNIGHT_FEAST_CRIMSON_HEAL_BONUS
    return f"Багровый пир лечит тебя на {_pct(total)} нанесённого урона вместо {_pct(base)}."


def _describe_blood_knight_shared_thirst(b: BuffDef) -> str:
    return (
        f"Когда ты лечишься от нанесённого урона, {_pct(bc.BLOOD_KNIGHT_SHARED_THIRST_ALLY_HEAL_PCT)} "
        f"этого лечения получает союзник с самым низким здоровьем. {_ALLIES_ONLY}"
    )


def _describe_blood_knight_blood_pact(b: BuffDef) -> str:
    base = bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST
    reduced = base * (1.0 - bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION)
    return (
        f"Багровый пир забирает у тебя {_pct(reduced)} текущего здоровья вместо {_pct(base)}."
    )


def _describe_blood_knight_shared_feast(b: BuffDef) -> str:
    return f"Весь твой урон (обычная атака и навыки) больше на {_pct(bc.BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS)}."


def _describe_poisoner_lingering_poison(b: BuffDef) -> str:
    base = bc.POISONER_POISON_DURATION_TICKS
    total = base + bc.POISONER_LINGERING_POISON_BONUS_TURNS
    return f"Яд от Отравленного клинка держится {_turns(total)} вместо {base}."


# --- Отравитель, микробаффы патча 56 ---


def _poisoner_base_vuln() -> float:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["poisoner_decay"].effect_value


def _poisoner_base_disrupt_chance() -> float:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["poisoner_disrupt"].effect_value


# --- Клинок теней, микробаффы патча 56 ---


def _describe_shadow_blade_deadly_precision(b: BuffDef) -> str:
    return (
        f"Шанс критического удара +{_points(bc.SHADOW_BLADE_DEADLY_PRECISION_CRIT)} "
        "(прибавляется к твоему: было 20% - станет 32%)."
    )


def _describe_shadow_blade_carve(b: BuffDef) -> str:
    return (
        f"Если Жатва меток тратит {bc.SHADOW_BLADE_CARVE_MIN_STACKS} или больше зарядов Метки и бьёт критически, "
        f"урон умножается на {bc.SHADOW_BLADE_CARVE_CRIT_MULT:g} вместо обычных {bc.CRIT_MULTIPLIER:g}."
    )


def _describe_shadow_blade_bloodlust(b: BuffDef) -> str:
    return (
        "После твоего критического удара следующий удар тоже будет критическим. "
        f"Срабатывает не чаще раза в {_turns(bc.SHADOW_BLADE_BLOODLUST_COOLDOWN)}."
    )


def _describe_shadow_blade_mark_of_prey_plus(b: BuffDef) -> str:
    return (
        f"Обычная атака с шансом {_pct(bc.SHADOW_BLADE_MARK_ON_ATTACK_CHANCE)} вешает на цель ещё один заряд "
        f"Метки добычи (всего зарядов может быть не больше {bc.SHADOW_BLADE_MARK_MAX_STACKS})."
    )


def _describe_shadow_blade_shadow(b: BuffDef) -> str:
    return (
        f"Шанс уклониться от удара +{_points(bc.SHADOW_BLADE_SHADOW_DODGE)} "
        "(прибавляется к твоему: было 30% - станет 38%)."
    )


def _describe_shadow_blade_slip_away(b: BuffDef) -> str:
    return (
        f"После того как ты уклонился, шанс уклониться от следующего удара +{_points(bc.SHADOW_BLADE_SLIP_AWAY)}."
    )


def _describe_shadow_blade_blade_dancer(b: BuffDef) -> str:
    return (
        f"Когда ты уклоняешься, Метки добычи, которые уже висят на врагах, снова держатся "
        f"{_turns(bc.SHADOW_BLADE_MARK_DURATION)}."
    )


def _describe_shadow_blade_blade_hunger(b: BuffDef) -> str:
    return "Когда ты уклоняешься, тот, кто промахнулся, получает заряд Метки добычи."


def _describe_shadow_blade_hunters_solitude(b: BuffDef) -> str:
    return (
        f"Пока ты дерёшься один, без союзников, весь твой урон больше на {_pct(bc.SHADOW_BLADE_SOLO_DAMAGE)}."
    )


def _describe_shadow_blade_second_chance(b: BuffDef) -> str:
    return (
        f"Каждый {bc.SHADOW_BLADE_SECOND_CHANCE_INTERVAL}-й ход боя первый удар по тебе "
        "гарантированно промахивается."
    )


def _describe_shadow_blade_mark_passed_on(b: BuffDef) -> str:
    return (
        f"Союзники чаще бьют критически по цели с твоей Меткой добычи: их шанс +{_points(bc.SHADOW_BLADE_ALLY_CRIT_ON_MARK)}. "
        f"{_ALLIES_ONLY}"
    )


def _describe_shadow_blade_inspiration(b: BuffDef) -> str:
    return (
        f"Когда цель с твоей Меткой погибает, союзники восстанавливают {_pct(bc.SHADOW_BLADE_INSPIRATION_HEAL)} "
        f"максимального здоровья и {_turns(bc.SHADOW_BLADE_INSPIRATION_TURNS)} бьют на "
        f"{_pct(bc.SHADOW_BLADE_INSPIRATION_DAMAGE)} сильнее. {_ALLIES_ONLY}"
    )


def _describe_shadow_blade_hunting_mark(b: BuffDef) -> str:
    return (
        f"Союзники видят в сводке боя, на ком висит твоя Метка добычи и сколько у неё зарядов. {_ALLIES_ONLY}"
    )


def _describe_poisoner_toxic_blood(b: BuffDef) -> str:
    base = _poisoner_base_vuln()
    total = base + bc.POISONER_TOXIC_BLOOD_VULN_BONUS
    return (
        f"Разложение делает цель уязвимее сильнее: урон по ней больше на {_pct(total)} вместо {_pct(base)}. "
        f"Кроме того, все остальные враги, которых ты отравил, тоже становятся уязвимее - на "
        f"{_pct(bc.POISONER_TOXIC_BLOOD_SPREAD_PCT)} от этой силы."
    )


def _describe_poisoner_desiccation(b: BuffDef) -> str:
    total = bc.POISONER_DISRUPT_WEAKEN + bc.POISONER_DESICCATION_WEAKEN_BONUS
    return (
        f"Дурманящий дротик ослабляет цель сильнее: она бьёт на {_pct(total)} слабее вместо "
        f"{_pct(bc.POISONER_DISRUPT_WEAKEN)}. Кроме того, все остальные враги, которых ты отравил, "
        f"тоже ослабевают - на {_pct(bc.POISONER_DESICCATION_SPREAD_PCT)} от этой силы."
    )


def _describe_poisoner_double_dose(b: BuffDef) -> str:
    return (
        f"Разложение с шансом {_pct(bc.POISONER_DOUBLE_DOSE_CHANCE)} не только делает цель уязвимее, "
        "но и ослабляет её (как Дурманящий дротик)."
    )


def _describe_poisoner_corroding_toxin(b: BuffDef) -> str:
    return f"Твой яд наносит на {_pct(bc.POISONER_CORRODING_TOXIN_BONUS)} больше урона."


def _describe_poisoner_necrosis(b: BuffDef) -> str:
    total = bc.POISONER_NECROSIS_PER_STACK * bc.POISONER_MAX_STACKS
    return (
        f"Чем больше зарядов яда на цели, тем сильнее он жжёт: +{_pct(bc.POISONER_NECROSIS_PER_STACK)} "
        f"урона яда за каждый заряд, до +{_pct(total)} при {bc.POISONER_MAX_STACKS} зарядах."
    )


def _describe_poisoner_toxic_burst(b: BuffDef) -> str:
    return (
        "Когда яд на цели заканчивается, он напоследок наносит ещё "
        f"{_pct(bc.POISONER_TOXIC_BURST_EXPIRE_PCT)} от своего урона за ход."
    )


def _describe_poisoner_plague(b: BuffDef) -> str:
    return (
        "Если отравленный враг погибает, его яд переходит на другого врага с тем же числом зарядов "
        f"(но вполсилы). {_MANY_ENEMIES}"
    )


def _describe_poisoner_epidemic(b: BuffDef) -> str:
    return "Если взята и Зараза: перешедший на другого врага яд бьёт в полную силу, а не вполсилы."


def _describe_poisoner_venom_cloud(b: BuffDef) -> str:
    return (
        f"Каждый {bc.POISONER_VENOM_CLOUD_INTERVAL}-й ход Отравленный клинок отравляет сразу всех врагов, "
        f"а не одного. {_MANY_ENEMIES}"
    )


def _describe_poisoner_hallucinogen(b: BuffDef) -> str:
    base = _poisoner_base_disrupt_chance()
    total = base + bc.POISONER_HALLUCINOGEN_BONUS
    return f"Дурманящий дротик сбивает действие цели с шансом {_pct(total)} вместо {_pct(base)}."


def _describe_poisoner_paralytic(b: BuffDef) -> str:
    return (
        "Когда Дурманящий дротик сбил действие цели, на 1 ход её проще оглушить или заморозить: "
        f"её защита от этого -{_points(bc.POISONER_PARALYTIC_RESIST_DOWN)}."
    )


def _describe_poisoner_toxicology(b: BuffDef) -> str:
    return (
        f"{_pct(bc.POISONER_TOXICOLOGY_SHIELD_PIERCE)} урона яда проходит сквозь щит цели прямо в здоровье. "
        "Выносливость цели яд и так не уменьшает."
    )


def _describe_elementalist_deep_freeze(b: BuffDef) -> str:
    return (
        f"Ледяные оковы чаще замораживают цель: шанс +{_points(bc.ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS)} "
        "(цель с высокой Волей всё равно может устоять)."
    )


def _describe_elementalist_numbness(b: BuffDef) -> str:
    base = bc.CONTROL_BASE_DURATION_TICKS
    total = base + bc.ELEMENTALIST_NUMBNESS_FREEZE_BONUS_TURNS
    return (
        f"Заморозка от Ледяных оков держится {_turns(total)} вместо {base}. "
        "На игроков не действует - их замораживает на 1 ход, как обычно."
    )


def _describe_elementalist_thrift(b: BuffDef) -> str:
    return (
        f"С шансом {_pct(bc.ELEMENTALIST_ECONOMY_NO_COOLDOWN_CHANCE)} навык после применения не уходит на "
        "перезарядку - его можно сразу применить снова."
    )


def _describe_elementalist_overload(b: BuffDef) -> str:
    return (
        f"Раз в {_turns(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS)} следующий навык не уходит на перезарядку - "
        "его можно сразу применить снова."
    )


def _describe_elementalist_elemental_flow(b: BuffDef) -> str:
    return (
        "Примени три разных стихийных навыка подряд (огонь, лёд, молния) - следующее действие нанесёт "
        f"на {_pct(bc.ELEMENTALIST_ELEMENTAL_FLOW_BONUS)} больше урона."
    )


def _describe_elementalist_flame_power(b: BuffDef) -> str:
    return (
        f"Огненная плеть бьёт на {_pct(bc.ELEMENTALIST_FLAME_POWER_BONUS)} сильнее. "
        "Если взята и Всеобщая стихия, на этот навык действует только больший из двух бонусов."
    )


def _describe_elementalist_frost_power(b: BuffDef) -> str:
    return (
        f"Ледяные оковы бьют на {_pct(bc.ELEMENTALIST_FROST_POWER_BONUS)} сильнее. "
        "Если взята и Всеобщая стихия, на этот навык действует только больший из двух бонусов."
    )


def _describe_elementalist_storm_power(b: BuffDef) -> str:
    return (
        f"Цепь молний бьёт на {_pct(bc.ELEMENTALIST_STORM_POWER_BONUS)} сильнее. "
        "Если взята и Всеобщая стихия, на этот навык действует только больший из двух бонусов."
    )


def _describe_elementalist_universal_element(b: BuffDef) -> str:
    return (
        f"Все стихийные навыки (огонь, лёд, молния) бьют на {_pct(bc.ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS)} сильнее. "
        "Если на навык есть свой бафф мощи (Пламенная, Ледяная, Мощь бури), действует только больший из двух."
    )


def _describe_elementalist_heat_shock(b: BuffDef) -> str:
    return (
        "Когда Горение на цели заканчивается, на 1 ход её проще оглушить или заморозить: "
        f"её защита от этого -{_points(bc.ELEMENTALIST_HEAT_SHOCK_RESIST_DOWN)}."
    )


def _describe_elementalist_chain_lightning(b: BuffDef) -> str:
    base = 2
    total = base + bc.ELEMENTALIST_CHAIN_LIGHTNING_EXTRA_TARGETS
    return f"Цепь молний бьёт ещё {total} врагов кроме основной цели вместо {base}."


def _describe_elementalist_firestorm(b: BuffDef) -> str:
    return (
        "Горение от Огненной плети перекидывается на остальных врагов - на них оно жжёт "
        f"в {_pct(bc.ELEMENTALIST_FIRESTORM_SPREAD_PCT)} силы. {_MANY_ENEMIES}"
    )


def _describe_elementalist_ice_field(b: BuffDef) -> str:
    return (
        "Когда Ледяные оковы замораживают цель, остальных врагов на 1 ход проще оглушить или "
        f"заморозить: их защита от этого -{_points(bc.ELEMENTALIST_ICE_FIELD_CHILL_PCT)}. {_MANY_ENEMIES}"
    )


# --- Тёмный мистик, микробаффы патча 56 ---


def _pact_conversion() -> float:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["dark_mystic_blood_pact"].effect_value


def _ward_cd() -> int:
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    return SUBCLASS_SKILL_DEFS["dark_mystic_ward"].cd


def _describe_dark_mystic_blood_bond(b: BuffDef) -> str:
    base = _pact_conversion()
    return (
        f"Кровавый пакт превращает в лечение {_pct(base + bc.DARK_MYSTIC_BLOOD_BOND_BONUS)} "
        f"нанесённого урона вместо {_pct(base)}."
    )


def _describe_dark_mystic_dark_resonance(b: BuffDef) -> str:
    base = _pact_conversion()
    return (
        f"Если у того, кого лечит Кровавый пакт, меньше {_pct(bc.DARK_MYSTIC_RESONANCE_HP_THRESHOLD)} здоровья, "
        f"в лечение идёт ещё {_points(bc.DARK_MYSTIC_RESONANCE_BONUS)} урона "
        f"(было {_pct(base)} - станет {_pct(base + bc.DARK_MYSTIC_RESONANCE_BONUS)})."
    )


def _describe_dark_mystic_blood_pact_plus(b: BuffDef) -> str:
    return (
        f"Навыки, которые забирают твоё здоровье, забирают на {_pct(bc.DARK_MYSTIC_HP_COST_REDUCTION)} меньше."
    )


def _describe_dark_mystic_self_denial(b: BuffDef) -> str:
    return (
        f"Пока у тебя больше {_pct(bc.DARK_MYSTIC_SELF_DENIAL_MIN_HP)} здоровья, Кровавый пакт забирает у тебя "
        f"ещё {_pct(bc.DARK_MYSTIC_SELF_DENIAL_EXTRA_HP)} максимального здоровья, но бьёт и лечит на "
        f"{_pct(bc.DARK_MYSTIC_SELF_DENIAL_BONUS)} сильнее."
    )


def _describe_dark_mystic_dark_reward(b: BuffDef) -> str:
    return (
        "После навыка, который забрал твоё здоровье, следующий Кровавый пакт бьёт и лечит на "
        f"{_pct(bc.DARK_MYSTIC_DARK_REWARD_BONUS)} сильнее."
    )


def _describe_dark_mystic_edge(b: BuffDef) -> str:
    return (
        f"Пока у тебя меньше {_pct(bc.DARK_MYSTIC_EDGE_HP_THRESHOLD)} здоровья, твой урон и лечение "
        f"больше на {_pct(bc.DARK_MYSTIC_EDGE_BONUS)}."
    )


def _describe_dark_mystic_blood_ward(b: BuffDef) -> str:
    return f"Щит от Оберега больше на {_pct(bc.DARK_MYSTIC_WARD_SHIELD_BONUS)}."


def _describe_dark_mystic_ward_passed_on(b: BuffDef) -> str:
    return (
        "Оберег ставит такой же щит, как тебе, ещё и союзнику с самым низким здоровьем. "
        f"{_ALLIES_ONLY}"
    )


def _describe_dark_mystic_steadfast_ward(b: BuffDef) -> str:
    cd = _ward_cd()
    return (
        f"Щит от Оберега больше на {_pct(bc.DARK_MYSTIC_STEADFAST_WARD_BONUS)}, но Оберег перезаряжается "
        f"{_turns(cd + bc.DARK_MYSTIC_STEADFAST_WARD_CD)} вместо {cd}."
    )


def _describe_dark_mystic_shared_pact(b: BuffDef) -> str:
    return (
        "Кровавый пакт лечит ещё одного союзника - второго по тяжести раненого: он получает "
        f"{_pct(bc.DARK_MYSTIC_SHARED_PACT_PCT)} от основного лечения. {_ALLIES_ONLY}"
    )


def _describe_dark_mystic_circle_of_darkness(b: BuffDef) -> str:
    return (
        f"Каждый {bc.DARK_MYSTIC_CIRCLE_INTERVAL}-й ход Кровавый пакт лечит ещё и всех союзников - "
        f"каждого на {_pct(bc.DARK_MYSTIC_CIRCLE_PCT)} от основного лечения. {_ALLIES_ONLY}"
    )


def _describe_dark_mystic_echo(b: BuffDef) -> str:
    return (
        f"{round(bc.DARK_MYSTIC_ECHO_PCT * 100)}% лечения, которое не влезло (цель уже полностью здорова), "
        f"становится щитом для союзника с самым низким здоровьем на {_turns(bc.DARK_MYSTIC_ECHO_DURATION)}, "
        f"не больше {round(bc.DARK_MYSTIC_ECHO_CAP_PCT * 100)}% его здоровья. Несбитый остаток сгорает, "
        f"в лечение не превращается. {_ALLIES_ONLY}"
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
    "guardian_sturdy_armor": _describe_guardian_sturdy_armor,
    "guardian_reflection": _describe_guardian_reflection,
    "guardian_resilience": _describe_guardian_resilience,
    "guardian_command": _describe_guardian_command,
    "guardian_provoker_mark": _describe_guardian_provoker_mark,
    "guardian_guard": _describe_guardian_guard,
    "guardian_allys_shield": _describe_guardian_allys_shield,
    "guardian_wall": _describe_guardian_wall,
    "guardian_counterattack": _describe_guardian_counterattack,
    "poisoner_lingering_poison": _describe_poisoner_lingering_poison,
    "shadow_blade_deadly_precision": _describe_shadow_blade_deadly_precision,
    "shadow_blade_carve": _describe_shadow_blade_carve,
    "shadow_blade_bloodlust": _describe_shadow_blade_bloodlust,
    "shadow_blade_mark_of_prey_plus": _describe_shadow_blade_mark_of_prey_plus,
    "shadow_blade_shadow": _describe_shadow_blade_shadow,
    "shadow_blade_slip_away": _describe_shadow_blade_slip_away,
    "shadow_blade_blade_dancer": _describe_shadow_blade_blade_dancer,
    "shadow_blade_blade_hunger": _describe_shadow_blade_blade_hunger,
    "shadow_blade_hunters_solitude": _describe_shadow_blade_hunters_solitude,
    "shadow_blade_second_chance": _describe_shadow_blade_second_chance,
    "shadow_blade_mark_passed_on": _describe_shadow_blade_mark_passed_on,
    "shadow_blade_inspiration": _describe_shadow_blade_inspiration,
    "shadow_blade_hunting_mark": _describe_shadow_blade_hunting_mark,
    "poisoner_toxic_blood": _describe_poisoner_toxic_blood,
    "poisoner_desiccation": _describe_poisoner_desiccation,
    "poisoner_double_dose": _describe_poisoner_double_dose,
    "poisoner_corroding_toxin": _describe_poisoner_corroding_toxin,
    "poisoner_necrosis": _describe_poisoner_necrosis,
    "poisoner_toxic_burst": _describe_poisoner_toxic_burst,
    "poisoner_plague": _describe_poisoner_plague,
    "poisoner_epidemic": _describe_poisoner_epidemic,
    "poisoner_venom_cloud": _describe_poisoner_venom_cloud,
    "poisoner_hallucinogen": _describe_poisoner_hallucinogen,
    "poisoner_paralytic": _describe_poisoner_paralytic,
    "poisoner_toxicology": _describe_poisoner_toxicology,
    "dark_mystic_blood_bond": _describe_dark_mystic_blood_bond,
    "dark_mystic_dark_resonance": _describe_dark_mystic_dark_resonance,
    "dark_mystic_blood_pact_plus": _describe_dark_mystic_blood_pact_plus,
    "dark_mystic_self_denial": _describe_dark_mystic_self_denial,
    "dark_mystic_dark_reward": _describe_dark_mystic_dark_reward,
    "dark_mystic_edge": _describe_dark_mystic_edge,
    "dark_mystic_blood_ward": _describe_dark_mystic_blood_ward,
    "dark_mystic_ward_passed_on": _describe_dark_mystic_ward_passed_on,
    "dark_mystic_steadfast_ward": _describe_dark_mystic_steadfast_ward,
    "dark_mystic_shared_pact": _describe_dark_mystic_shared_pact,
    "dark_mystic_circle_of_darkness": _describe_dark_mystic_circle_of_darkness,
    "dark_mystic_echo": _describe_dark_mystic_echo,
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
    "control_utility": "Контроль и польза",
    "group_support": "Групповая поддержка",
    "healing": "Лечение",
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
