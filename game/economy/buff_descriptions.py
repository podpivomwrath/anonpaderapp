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
    return f"Провокация от Удара щитом длится {_turns(total)} вместо {base}."


def _describe_guardian_vital_block(b: BuffDef) -> str:
    return f"Лечит на {_pct(bc.GUARDIAN_HEAL_ON_BLOCK)} от максимального HP при успешном блоке."




def _describe_guardian_heavy_hand(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.GUARDIAN_HEAVY_HAND_BONUS)}."


# --- Страж, микробаффы патча 56 ---


def _describe_guardian_sturdy_armor(b: BuffDef) -> str:
    return f"Входящий урон снижен на {_points(bc.GUARDIAN_STURDY_ARMOR_REDUCTION)}."


def _describe_guardian_reflection(b: BuffDef) -> str:
    return (
        f"При полном блоке {_pct(bc.GUARDIAN_REFLECTION_PCT)} заблокированного урона "
        "возвращается атакующему."
    )


def _describe_guardian_resilience(b: BuffDef) -> str:
    return (
        f"Пока здоровье ниже {_pct(bc.GUARDIAN_RESILIENCE_HP_THRESHOLD)}, входящий урон "
        f"снижен дополнительно на {_points(bc.GUARDIAN_RESILIENCE_REDUCTION)}."
    )


def _describe_guardian_command(b: BuffDef) -> str:
    return (
        f"Мобы выбирают Стража целью на {_pct(bc.GUARDIAN_COMMAND_AGGRO_BONUS)} чаще. "
        "Работает только в PvE и рейдах."
    )


def _describe_guardian_provoker_mark(b: BuffDef) -> str:
    total = bc.PROVOKE_PVP_DAMAGE_REDUCTION + bc.GUARDIAN_PROVOKER_MARK_BONUS
    return (
        f"В PvP противник, ударивший не по Стражу, наносит на {_pct(total)} меньше урона "
        f"вместо {_pct(bc.PROVOKE_PVP_DAMAGE_REDUCTION)}."
    )


def _describe_guardian_guard(b: BuffDef) -> str:
    total = bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE + bc.GUARDIAN_GUARD_BLOCK_BONUS
    return (
        f"Шанс полного блока вместе с Несокрушимостью: {_pct(total)} "
        f"вместо {_pct(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE)}."
    )


def _describe_guardian_allys_shield(b: BuffDef) -> str:
    return (
        f"Союзник с наименьшим запасом здоровья получает {_pct(bc.GUARDIAN_ALLYS_SHIELD_SHARE)} "
        "защиты Глухой обороны. Только в бою с союзниками, в одиночку эффекта нет."
    )


def _describe_guardian_wall(b: BuffDef) -> str:
    return (
        "Глухая оборона снимает один отрицательный эффект с союзника, у которого меньше "
        "всего здоровья. Только в бою с союзниками, в одиночку эффекта нет."
    )


def _describe_guardian_counterattack(b: BuffDef) -> str:
    return (
        f"При полном блоке Страж бьёт в ответ с силой {_pct(bc.GUARDIAN_COUNTERATTACK_MULT)} "
        "от обычной атаки."
    )


def _describe_guardian_retribution(b: BuffDef) -> str:
    return (
        f"За каждые 10% максимального здоровья, срезанные блоком за последние "
        f"{_turns(bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS)}, урон растёт на "
        f"{_pct(bc.GUARDIAN_RETRIBUTION_PER_10PCT)}. Потолок: {_pct(bc.GUARDIAN_RETRIBUTION_CAP)}."
    )


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
    return f"Кап лечения за ход - {_pct(total)} от maxHP вместо {_pct(bc.BLOOD_KNIGHT_HEAL_CAP_PER_TURN)}."


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
        f"самому раненому живому союзнику. Не действует в бою 1×1 - союзников нет."
    )


def _describe_blood_knight_blood_pact(b: BuffDef) -> str:
    base = bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST
    reduced = base * (1.0 - bc.BLOOD_KNIGHT_BLOOD_PACT_COST_REDUCTION)
    return f"Себестоимость HP Багрового пира - {_pct(reduced)} текущего HP вместо {_pct(base)}."


def _describe_blood_knight_shared_feast(b: BuffDef) -> str:
    return f"Урон всеми навыками увеличен на {_pct(bc.BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS)}."


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
    return f"Шанс крита увеличен на {_points(bc.SHADOW_BLADE_DEADLY_PRECISION_CRIT)}."


def _describe_shadow_blade_carve(b: BuffDef) -> str:
    return (
        f"Если Жатва тратит {bc.SHADOW_BLADE_CARVE_MIN_STACKS} и больше стаков Метки, крит бьёт "
        f"в {bc.SHADOW_BLADE_CARVE_CRIT_MULT} раза вместо {bc.CRIT_MULTIPLIER}."
    )


def _describe_shadow_blade_bloodlust(b: BuffDef) -> str:
    return (
        f"После крита следующий удар критует гарантированно. Не чаще раза в "
        f"{_turns(bc.SHADOW_BLADE_BLOODLUST_COOLDOWN)}."
    )


def _describe_shadow_blade_mark_of_prey_plus(b: BuffDef) -> str:
    return (
        f"Обычная атака с шансом {_pct(bc.SHADOW_BLADE_MARK_ON_ATTACK_CHANCE)} добавляет стак "
        f"Метки добычи. Максимум стаков: {bc.SHADOW_BLADE_MARK_MAX_STACKS}."
    )


def _describe_shadow_blade_shadow(b: BuffDef) -> str:
    return f"Шанс уклонения увеличен на {_points(bc.SHADOW_BLADE_SHADOW_DODGE)}."


def _describe_shadow_blade_slip_away(b: BuffDef) -> str:
    return (
        f"После удачного уворота следующий удар по Клинку теней имеет на "
        f"{_points(bc.SHADOW_BLADE_SLIP_AWAY)} меньше шансов попасть."
    )


def _describe_shadow_blade_blade_dancer(b: BuffDef) -> str:
    return f"Удачный уворот продлевает уже висящие Метки добычи до {_turns(bc.SHADOW_BLADE_MARK_DURATION)}."


def _describe_shadow_blade_blade_hunger(b: BuffDef) -> str:
    return "Каждый удачный уворот добавляет стак Метки добычи тому, кто промахнулся."


def _describe_shadow_blade_hunters_solitude(b: BuffDef) -> str:
    return (
        f"Урон увеличен на {_pct(bc.SHADOW_BLADE_SOLO_DAMAGE)}, пока Клинок теней дерётся без "
        "союзников."
    )


def _describe_shadow_blade_second_chance(b: BuffDef) -> str:
    return (
        f"Каждый {bc.SHADOW_BLADE_SECOND_CHANCE_INTERVAL}-й ход удар по Клинку теней "
        "гарантированно проходит мимо."
    )


def _describe_shadow_blade_mark_passed_on(b: BuffDef) -> str:
    return (
        f"Союзники критуют по цели с Меткой добычи на {_points(bc.SHADOW_BLADE_ALLY_CRIT_ON_MARK)} "
        "чаще. Только в бою с союзниками, в одиночку эффекта нет."
    )


def _describe_shadow_blade_inspiration(b: BuffDef) -> str:
    return (
        f"Добив цель с Меткой, союзники восстанавливают {_pct(bc.SHADOW_BLADE_INSPIRATION_HEAL)} "
        f"максимального здоровья и получают {_pct(bc.SHADOW_BLADE_INSPIRATION_DAMAGE)} к урону на "
        f"{_turns(bc.SHADOW_BLADE_INSPIRATION_TURNS)}. Только в бою с союзниками."
    )


def _describe_shadow_blade_hunting_mark(b: BuffDef) -> str:
    return (
        "Метка добычи и число её стаков видны союзникам в боевой сводке. Только в бою с "
        "союзниками."
    )


def _describe_poisoner_toxic_blood(b: BuffDef) -> str:
    base = _poisoner_base_vuln()
    total = base + bc.POISONER_TOXIC_BLOOD_VULN_BONUS
    return (
        f"Уязвимость от Разложения: {_pct(total)} вместо {_pct(base)}. Вдобавок она ложится "
        f"на всех отравленных тобой врагов силой {_pct(bc.POISONER_TOXIC_BLOOD_SPREAD_PCT)} "
        "от основной."
    )


def _describe_poisoner_desiccation(b: BuffDef) -> str:
    total = bc.POISONER_DISRUPT_WEAKEN + bc.POISONER_DESICCATION_WEAKEN_BONUS
    return (
        f"Ослабление от Дурманящего дротика: {_pct(total)} вместо {_pct(bc.POISONER_DISRUPT_WEAKEN)}. "
        f"Вдобавок оно ложится на всех отравленных тобой врагов силой "
        f"{_pct(bc.POISONER_DESICCATION_SPREAD_PCT)} от основного."
    )


def _describe_poisoner_double_dose(b: BuffDef) -> str:
    return (
        f"Разложение с шансом {_pct(bc.POISONER_DOUBLE_DOSE_CHANCE)} накладывает разом и "
        "Уязвимость, и Ослабление."
    )


def _describe_poisoner_corroding_toxin(b: BuffDef) -> str:
    return f"Урон яда увеличен на {_pct(bc.POISONER_CORRODING_TOXIN_BONUS)}."


def _describe_poisoner_necrosis(b: BuffDef) -> str:
    total = bc.POISONER_NECROSIS_PER_STACK * bc.POISONER_MAX_STACKS
    return (
        f"Урон яда растёт на {_pct(bc.POISONER_NECROSIS_PER_STACK)} за каждый стак на цели: "
        f"до {_pct(total)} при {bc.POISONER_MAX_STACKS} стаках."
    )


def _describe_poisoner_toxic_burst(b: BuffDef) -> str:
    return (
        f"Когда яд истекает, цель получает добавочный урон: "
        f"{_pct(bc.POISONER_TOXIC_BURST_EXPIRE_PCT)} от урона этого яда."
    )


def _describe_poisoner_plague(b: BuffDef) -> str:
    return (
        "Если отравленный противник погибает, яд переходит на следующего с тем же числом "
        "стаков. Нужен бой с несколькими противниками."
    )


def _describe_poisoner_epidemic(b: BuffDef) -> str:
    return "Перешедший по Заразе яд сохраняет полную силу вместо половинной."


def _describe_poisoner_venom_cloud(b: BuffDef) -> str:
    return (
        f"Каждый {bc.POISONER_VENOM_CLOUD_INTERVAL}-й ход Отравленный клинок накладывает стак "
        "яда на всех противников. Нужен бой с несколькими противниками."
    )


def _describe_poisoner_hallucinogen(b: BuffDef) -> str:
    base = _poisoner_base_disrupt_chance()
    total = base + bc.POISONER_HALLUCINOGEN_BONUS
    return f"Шанс сбить действие цели: {_pct(total)} вместо {_pct(base)}."


def _describe_poisoner_paralytic(b: BuffDef) -> str:
    return (
        f"После удачного сбоя сопротивление контролю цели снижено на "
        f"{_points(bc.POISONER_PARALYTIC_RESIST_DOWN)} на {_turns(1)}."
    )


def _describe_poisoner_toxicology(b: BuffDef) -> str:
    return (
        f"Яд проходит мимо {_pct(bc.POISONER_TOXICOLOGY_SHIELD_PIERCE)} щита цели. Митигацию "
        "яд не задевает и без этого баффа."
    )


def _describe_elementalist_deep_freeze(b: BuffDef) -> str:
    # Итоговый шанс зависит от WIL цели (control_resist) — заранее не считается.
    return f"Шанс наложить оглушение/заморозку Ледяными оковами увеличен на {_points(bc.ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS)}."


def _describe_elementalist_numbness(b: BuffDef) -> str:
    base = bc.CONTROL_BASE_DURATION_TICKS
    total = base + bc.ELEMENTALIST_NUMBNESS_FREEZE_BONUS_TURNS
    return (
        f"Заморозка от Ледяных оков длится {_turns(total)} вместо {base}. "
        "Против игроков длительность не растёт."
    )


def _describe_elementalist_thrift(b: BuffDef) -> str:
    return f"Шанс {_pct(bc.ELEMENTALIST_ECONOMY_NO_COOLDOWN_CHANCE)}, что применённый навык не уходит на перезарядку."


def _describe_elementalist_overload(b: BuffDef) -> str:
    return f"Раз в {_turns(bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS)} следующий применённый навык не уходит на перезарядку."


def _describe_elementalist_elemental_flow(b: BuffDef) -> str:
    return f"3 разных стихийных умения подряд усиливают следующее действие на {_pct(bc.ELEMENTALIST_ELEMENTAL_FLOW_BONUS)}."


def _describe_elementalist_flame_power(b: BuffDef) -> str:
    return (
        f"Урон Огненной плети увеличен на {_pct(bc.ELEMENTALIST_FLAME_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке - берётся больший бонус."
    )


def _describe_elementalist_frost_power(b: BuffDef) -> str:
    return (
        f"Урон Ледяных оков увеличен на {_pct(bc.ELEMENTALIST_FROST_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке - берётся больший бонус."
    )


def _describe_elementalist_storm_power(b: BuffDef) -> str:
    return (
        f"Урон Цепи молний увеличен на {_pct(bc.ELEMENTALIST_STORM_POWER_BONUS)}. "
        f"Не складывается со «Всеобщей стихией» на одном навыке - берётся больший бонус."
    )


def _describe_elementalist_universal_element(b: BuffDef) -> str:
    return (
        f"Урон всех стихийных навыков увеличен на {_pct(bc.ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS)}. "
        f"Не складывается с Пламенной/Ледяной мощью или Мощью бури на одном навыке - берётся больший бонус."
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
        f"Действует только в бою с несколькими противниками (массовый PvP) - в одиночном бою эффекта нет."
    )


def _describe_elementalist_ice_field(b: BuffDef) -> str:
    return (
        f"При заморозке основной цели Ледяными оковами сопротивление контролю других живых противников "
        f"снижается на {_points(bc.ELEMENTALIST_ICE_FIELD_CHILL_PCT)} на 1 ход. "
        f"Действует только в бою с несколькими противниками (массовый PvP) - в одиночном бою эффекта нет."
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
        f"Кровавый пакт обращает в лечение {_pct(base + bc.DARK_MYSTIC_BLOOD_BOND_BONUS)} "
        f"нанесённого урона вместо {_pct(base)}."
    )


def _describe_dark_mystic_dark_resonance(b: BuffDef) -> str:
    return (
        f"Если у цели лечения меньше {_pct(bc.DARK_MYSTIC_RESONANCE_HP_THRESHOLD)} здоровья, "
        f"Кровавый пакт обращает в лечение ещё на {_points(bc.DARK_MYSTIC_RESONANCE_BONUS)} больше."
    )


def _describe_dark_mystic_blood_pact_plus(b: BuffDef) -> str:
    return (
        f"Навыки, которые платят собственным здоровьем, стоят на "
        f"{_pct(bc.DARK_MYSTIC_HP_COST_REDUCTION)} дешевле."
    )


def _describe_dark_mystic_self_denial(b: BuffDef) -> str:
    return (
        f"Кровавый пакт дополнительно тратит {_pct(bc.DARK_MYSTIC_SELF_DENIAL_EXTRA_HP)} текущего "
        f"здоровья, но бьёт и лечит на {_pct(bc.DARK_MYSTIC_SELF_DENIAL_BONUS)} сильнее."
    )


def _describe_dark_mystic_dark_reward(b: BuffDef) -> str:
    return (
        f"После навыка, потратившего собственное здоровье, следующий Кровавый пакт сильнее на "
        f"{_pct(bc.DARK_MYSTIC_DARK_REWARD_BONUS)}."
    )


def _describe_dark_mystic_edge(b: BuffDef) -> str:
    return (
        f"Пока собственного здоровья меньше {_pct(bc.DARK_MYSTIC_EDGE_HP_THRESHOLD)}, урон и "
        f"лечение увеличены на {_pct(bc.DARK_MYSTIC_EDGE_BONUS)}."
    )


def _describe_dark_mystic_blood_ward(b: BuffDef) -> str:
    return f"Щит Оберега больше на {_pct(bc.DARK_MYSTIC_WARD_SHIELD_BONUS)}."


def _describe_dark_mystic_ward_passed_on(b: BuffDef) -> str:
    return (
        "Оберег накрывает вдобавок самого израненного союзника, полной величиной. "
        "Только в бою с союзниками."
    )


def _describe_dark_mystic_steadfast_ward(b: BuffDef) -> str:
    cd = _ward_cd()
    return (
        f"Оберег поглощает на {_pct(bc.DARK_MYSTIC_STEADFAST_WARD_BONUS)} больше урона, но "
        f"перезаряжается {_turns(cd + bc.DARK_MYSTIC_STEADFAST_WARD_CD)} вместо {cd}."
    )


def _describe_dark_mystic_shared_pact(b: BuffDef) -> str:
    return (
        f"Второму по тяжести раненому союзнику достаётся ещё "
        f"{_pct(bc.DARK_MYSTIC_SHARED_PACT_PCT)} лечения Кровавого пакта. "
        "Только в бою с союзниками."
    )


def _describe_dark_mystic_circle_of_darkness(b: BuffDef) -> str:
    return (
        f"Каждый {bc.DARK_MYSTIC_CIRCLE_INTERVAL}-й ход Кровавый пакт дополнительно лечит всех "
        f"союзников на {_pct(bc.DARK_MYSTIC_CIRCLE_PCT)} от основного лечения. "
        "Только в бою с союзниками."
    )


def _describe_dark_mystic_echo(b: BuffDef) -> str:
    return (
        f"Лечение сверх максимума здоровья не пропадает: оно становится щитом следующему по "
        f"низкому здоровью союзнику на {_turns(bc.DARK_MYSTIC_ECHO_DURATION)}. "
        "Только в бою с союзниками."
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
    "control_utility": "Контроль/утилита",
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
