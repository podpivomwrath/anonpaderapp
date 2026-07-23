"""Конфиг баланса — ВСЕ калибруемые константы в одном месте.

Версия формул: v2 (после первой итерации тестов в sim.js).
Баланс будет калиброваться дальше — не хардкодить эти значения по коду.
Значения с пометкой `TODO: content` — плейсхолдеры, контент допишется отдельно.
"""

# --- Статы и уровни ---
# Стартовые распределения ПО КЛАССАМ (онбординг-дизайн, суммарно 85).
# Отменяет прежнее правило «15 во все статы».
STARTING_STATS = {
    "warrior": {"STR": 25, "AGI": 15, "INT": 10, "VIT": 20, "WIL": 15},
    "rogue":   {"STR": 10, "AGI": 25, "INT": 15, "VIT": 15, "WIL": 20},
    "mage":    {"STR": 10, "AGI": 10, "INT": 25, "VIT": 15, "WIL": 25},
}
STARTING_STAT = 15            # базовое значение для мобов/тестовых болванок
STAT_POINTS_PER_LEVEL = 3     # прирост за уровень, распределяется вручную
MAX_LEVEL = 100               # конфигурируемый потолок (может стать 100+)

# Основной стат по базовому классу (до выбора подкласса)
PRIMARY_STAT_BY_CLASS = {"warrior": "str", "rogue": "agi", "mage": "int"}

# --- Опыт и уровни (progression-patch-4) ---
# character.experience = опыт, накопленный В ТЕКУЩЕМ уровне (сбрасывается при левелапе).
# xp_to_next(L) = XP_BASE * L**XP_EXP до 50; после 50 — «полка» (резкое замедление).
XP_BASE = 45
XP_EXP = 1.95
XP_PLATEAU_LEVEL = 50           # уровень излома кривой
XP_PLATEAU_SLOPE = 0.55        # наклон линейной «полки» после 50
XP_MOB_FLAT = 15               # опыт за моба: XP_MOB_FLAT + XP_MOB_PER_LEVEL * mob_level
XP_MOB_PER_LEVEL = 6
DEATH_XP_PENALTY = 0.20        # доля опыта ТЕКУЩЕГО уровня, теряемая при смерти

# --- Защита от чейн-контроля (diminishing returns) ---
CC_STREAK_REDUCE_AT = 3         # с какого подряд-контроля резать длительность
CC_STREAK_REDUCE_FACTOR = 0.5   # во сколько резать длительность
CC_IMMUNITY_AT = 4              # с какого подряд-контроля наступает иммунитет
CC_IMMUNITY_DURATION = 2        # длительность иммунитета к контролю, ходов

# --- Тиры экипировки ---
TIER_MULTIPLIERS = {
    "grey": 1.0,
    "white": 1.15,
    "green": 1.35,
    "blue": 1.6,
    "epic": 2.0,
    "legendary": 2.5,
}

# --- HP ---
HP_BASE = 60
HP_PER_LEVEL = 22
HP_PER_VIT = 8
HP_PER_TIER = 30

# --- Урон ---
WEAPON_BASE_PER_TIER = 10
K_DMG = {"str": 2.0, "int": 2.0, "agi": 1.5}  # Воин/Маг: 2, Разбойник: 1.5

# --- Крит ---
CRIT_PER_AGI = 0.003
CRIT_CAP = 0.60
CRIT_MULTIPLIER = 1.5

# --- Митигация ---
MITIGATION_PER_VIT = 0.002
MITIGATION_CAP = 0.50

# --- Воля ---
CONTROL_RESIST_PER_WIL = 0.01
CONTROL_RESIST_CAP = 0.75
SUPPORT_POWER_PER_WIL = 0.005  # без потолка

# --- Смерть и возрождение ---
RESPAWN_MIN_MINUTES = 1.0      # на 1 уровне
RESPAWN_MAX_MINUTES = 30.0     # на MAX_LEVEL
EXPERIENCE_LOSS_ON_DEATH = 0.20  # 20% опыта, накопленного к текущему уровню

# --- Таймеры ходов ---
PVP_GROUP_TURN_SECONDS = 60.0  # групповой PvP: окно хода 1 минута
DUEL_TURN_SECONDS = 60.0       # дуэль: ход 1 минута

# --- Ставки PvP ---
PVP_STAKE_PERCENT = 0.10  # доля farm-валюты проигравшего победителю; TODO: калибровка

# --- Пресеты баффов и респек ---
PRESET_MIN_BUFFS = 3
PRESET_MAX_BUFFS = 5
# категории, из которых обязателен хотя бы один бафф в пресете
PRESET_REQUIRED_CATEGORIES = {"defense", "control_utility"}
PRESET_CHANGE_COST_FARM = 500       # создание/изменение пресета; TODO: калибровка
CLASS_RESET_COST_DONATE = 100       # полный ресет класса; TODO: калибровка

# --- Подклассы и классовые испытания (патч 12) ---
SUBCLASS_UNLOCK_COST = 20000         # золото за выбор подкласса на 30 ур. (первый крупный сток)
SUBCLASS_UNLOCK_MIN_LEVEL = 30

# --- Заточка и пробуждение ---
ENCHANT_MAX_LEVEL = 20
ENCHANT_SUCCESS_CHANCE = 0.5        # TODO: content (может зависеть от уровня заточки)
AWAKENING_DESTRUCTION_CHANCE = 0.30
AWAKENING_REFUND_RATIO = 0.5        # частичный возврат ресурсов; TODO: content

# --- Биржа (игра — дилер) ---
EXCHANGE_BLOCK_SIZE = 100           # блок донат-валюты, за который цена делает шаг
EXCHANGE_BASE_BUY_PRICE = 100       # золота за 1 донат в нулевом блоке; TODO: калибровка
EXCHANGE_PRICE_STEP = 5             # ЛИНЕЙНЫЙ шаг цены за блок; TODO: калибровка
EXCHANGE_SPREAD = 15                # фикс. спред: sell = buy - spread (round-trip убыточен)
EXCHANGE_MIN_SELL_PRICE = 1

# --- Механики подклассов (плейсхолдеры; TODO: content) ---
GUARDIAN_BLOCK_REDUCTION = 0.5          # Блок: снижение входящего урона в этот тик
GUARDIAN_SHIELD_PER_VIT = 1.0           # Групповой щит: поглощение = VIT * коэф.
GUARDIAN_SHIELD_SELF_PENALTY = 0.5      # часть своей защиты уходит: митигация стража * (1-эта доля)
PROVOKE_PVP_DAMAGE_REDUCTION = 0.30     # PvP-провокация: урон по другим целям -30%
PROVOKE_PVP_DURATION_TICKS = 1

# --- Откалиброванные значения (патч балансировки, 5 итераций симуляции) ---
# Стартовые ориентиры для реальных баффов, НЕ финальные игровые числа.
# Дизайн-решение: Страж и Тёмный мистик осознанно слабы в чистых дуэлях 1×1
# (винрейт 20-28%) — компенсация через гир (8/8 PvE-выносливость, лучшие роли
# для рейдов), НЕ через баффы кита.

# Страж (микробаффы; значения продублированы в content/buffs.json)
GUARDIAN_BULWARK_FULL_BLOCK_CHANCE = 0.25   # Несокрушимость: шанс полного блока
GUARDIAN_COUNTERSTRIKE_MULT = 0.70          # Контрудар при блоке: от обычного удара
GUARDIAN_HEAL_ON_BLOCK = 0.08               # Живительный блок: хил % maxHP при блоке
GUARDIAN_HEAVY_HAND_BONUS = 0.10            # Тяжёлая рука: бонус к урону
GUARDIAN_PASSIVE_SUSTAIN_PER_TICK = 0.025   # Пассивная стойкость: самохил % maxHP вне блока

# Кровавый рыцарь
BLOOD_KNIGHT_RAGE_DAMAGE_BONUS = 0.05       # Кровавая ярость (урезано с +12%)
BLOOD_KNIGHT_LIFESTEAL_BASE = 0.09          # Ненасытность: % от нанесённого урона
BLOOD_KNIGHT_LIFESTEAL_LOW_HP_BONUS = 0.03  # доп. при HP ниже порога
BLOOD_KNIGHT_LIFESTEAL_LOW_HP_THRESHOLD = 0.5
# ОБЯЗАТЕЛЬНЫЙ кап: иначе лайфстил бесконтрольно скейлится с уроном на высоких уровнях
BLOOD_KNIGHT_HEAL_CAP_PER_TICK = 0.08       # % от maxHP за тик

# Отравитель — сила яда ОБЯЗАНА масштабироваться от статов (иначе класс
# математически нежизнеспособен независимо от текста способностей)
POISONER_POISON_WIL_COEF = 0.60             # вклад WIL в силу яда (на стак)
POISONER_POISON_AGI_COEF = 0.40             # вклад AGI
POISONER_MAX_STACKS = 3                     # тик-урон = сила яда / макс. стаки
POISONER_DIRECT_MULT = 0.90                 # штраф прямого урона за упор в дебаффы
POISONER_POISON_DURATION_TICKS = 3          # TODO: content — длительность не калибровалась

# Тёмный мистик (Кровавый пакт)
DARK_MYSTIC_PACT_MULT = 0.76                # прямой урон от обычного удара
DARK_MYSTIC_HEAL_CONVERSION_COEF = 1.75     # конверсия: support_power(WIL) * коэф + база
DARK_MYSTIC_HEAL_CONVERSION_BASE = 0.33
