"""Руны (2026-10-31, решения владельца - память runes-plan): каталог и числа.

Три вида: руны героя (общие, до 12 слотов), руны экипировки (уклон в класс,
слот у места снаряжения), руны навыков (по типу навыка, 2 слота на навык).

Руна - обычный предмет, продаётся и передаётся как выпала. Прокачивается не
руна, а личное мастерство игрока по виду руны: лишние копии «впитываются».
Эффективность от мастерства растёт по порогам (efficiency_of ниже), эффект
руны в слоте = value * эффективность.
"""

from dataclasses import dataclass, field

HERO, GEAR, SKILL = "hero", "gear", "skill"
KINDS = (HERO, GEAR, SKILL)
KIND_TITLES = {HERO: "Руны героя", GEAR: "Руны экипировки", SKILL: "Руны навыков"}

#: Кривые прогрессии: (копий до 110%, множитель последующих порогов).
#: Порог ступени k (100 + 10k %): k=1 - N0, дальше M * (k-1)^2. Тугие -
#: руны на шансы, вместо жёстких потолков (владелец, 2026-10-30).
CURVES: dict[str, tuple[int, int]] = {
    "normal": (81, 800),
    "tight": (162, 1600),
    "very_tight": (324, 3200),
}

#: Вес в розыгрыше выпавшей руны.
RARITY_WEIGHTS = {"common": 100, "rare": 30, "epic": 6, "mythic": 1}
RARITY_TITLES = {"common": "обычная", "rare": "редкая", "epic": "эпическая", "mythic": "мифическая"}

#: В PvP: full - в полную силу, half - вполсилы, none - не действует.
PVP_MULT = {"full": 1.0, "half": 0.5, "none": 0.0}

# --- Слоты ----------------------------------------------------------------------
HERO_SLOTS_FREE = 4
HERO_SLOTS_MAX = 12
#: Цена 5-го, 6-го ... 12-го слота: каждый втрое дороже (владелец: 7-8 у
#: среднего игрока, 10 - огромный вклад, 12 недостижим).
HERO_SLOT_PRICES = [35_000, 100_000, 300_000, 900_000, 2_700_000, 8_000_000, 24_000_000, 72_000_000]
SKILL_SLOTS_MAX = 2
SKILL_SLOT_PRICE = 60_000
#: Пока нет заточки - по одному слоту на место снаряжения.
GEAR_PLACES = ("weapon", "helmet", "armor", "legs", "boots")
GEAR_SLOTS_PER_PLACE = 1
ARMOR_PLACES = ("helmet", "armor", "legs", "boots")

# --- Выпадение (для теста; настраиваем по живой игре) ---------------------------
#: Шанс руны за победу над мобом клетки.
MOB_DROP_CHANCE = 0.10
#: Доля руны каждого вида в розыгрыше.
KIND_WEIGHTS = {HERO: 50, GEAR: 30, SKILL: 20}


@dataclass(frozen=True)
class RuneDef:
    id: str
    kind: str
    name: str
    #: Эффект при 100% эффективности, в долях (0.04 = 4%).
    value: float
    #: Что делает, «{v}» заменяется на текущее значение.
    text: str
    rarity: str = "common"
    curve: str = "normal"
    pvp: str = "full"
    #: Руны экипировки и навыков: базовые классы, которым подходит (пусто - всем).
    classes: tuple[str, ...] = ()
    #: Руны экипировки: "weapon" или "armor".
    place: str = ""
    #: Руны навыков: тег навыка (SKILL_TAGS), пусто - любой навык.
    tag: str = ""
    #: Эффект уже подключён к игре.
    ready: bool = True
    emoji: str = "🔹"
    extra: dict = field(default_factory=dict)


W, R, M = "warrior", "rogue", "mage"

RUNES: list[RuneDef] = [
    # --- Руны героя ---------------------------------------------------------------
    RuneDef("ash_skin", HERO, "Пепельная кожа", 0.04, "+{v} к здоровью", pvp="half"),
    RuneDef("doorstep_rush", HERO, "Рывок с порога", 0.12, "+{v} урона в первые 2 хода боя", pvp="half"),
    RuneDef("spare_breath", HERO, "Запас дыхания", 0.10,
            "раз за бой, когда здоровья меньше 30%, лечит {v} от максимума", pvp="half", rarity="rare", ready=False),
    RuneDef("stubborn_brow", HERO, "Упрямый лоб", 0.08, "+{v} к сопротивлению контролю", pvp="half", ready=False),
    RuneDef("bitter_blood", HERO, "Горькая кровь", 0.12, "урон от ядов, горения и кровотечений меньше на {v}",
            pvp="half", ready=False),
    RuneDef("heavy_gaze", HERO, "Тяжёлый взгляд", 0.06, "у мобов клетки на {v} меньше здоровья", pvp="none", ready=False),
    RuneDef("grabby_fingers", HERO, "Цепкие пальцы", 0.10, "+{v} к шансу, что с моба выпадет вещь", pvp="none"),
    RuneDef("junk_nose", HERO, "Нюх старьёвщика", 0.15, "+{v} к шансу лишней реликвии с моба", pvp="none", rarity="rare"),
    RuneDef("keen_eye", HERO, "Намётанный глаз", 0.06,
            "шанс {v}, что выпавшая вещь будет на ступень редкости выше", pvp="none", rarity="rare",
            curve="tight"),
    RuneDef("tight_purse", HERO, "Тугой кошель", 0.08, "скупщик платит за реликвии больше на {v}", pvp="none"),
    RuneDef("battered", HERO, "Битый опыт", 0.15, "плохой исход события на {v} реже", ready=False),
    RuneDef("crooked_path", HERO, "Кривая тропа", 0.10, "+{v} к шансу события при исследовании", ready=False),
    RuneDef("stone_sleep", HERO, "Сон на камне", 0.20, "отдых быстрее на {v}"),
    RuneDef("tenacious", HERO, "Живучий", 0.20, "воскрешение быстрее на {v}"),
    RuneDef("light_saddle", HERO, "Лёгкое седло", 0.08, "маунт быстрее на {v}"),
    RuneDef("miner_sense", HERO, "Чутьё забойщика", 0.08, "добыча руды быстрее на {v}"),
    RuneDef("heavy_catch", HERO, "Тяжёлый улов", 0.04, "+{v} к доле веса рыбы"),
    RuneDef("green_fingers", HERO, "Зелёные пальцы", 0.08, "+{v} к шансу второй травы"),
    RuneDef("clean_still", HERO, "Чистая перегонка", 0.10, "эликсиры сильнее на {v}", pvp="half", ready=False),
    RuneDef("full_belly", HERO, "Сытый живот", 0.20, "еда держится дольше на {v}"),
    RuneDef("calluses", HERO, "Мозоли", 0.06, "+{v} к опыту ремёсел", ready=False),
    RuneDef("monolith_mark", HERO, "Метка Монолита", 0.05, "+{v} к опыту героя", rarity="epic", curve="tight"),
    RuneDef("loose_tongue", HERO, "Язык без костей", 0.05, "обоз привозит больше золота на {v}", rarity="epic",
            curve="tight"),

    # --- Руны экипировки ----------------------------------------------------------
    RuneDef("hammer_down", GEAR, "Молот по лежачему", 0.15, "+{v} урона по оглушённым", pvp="half",
            classes=(W,), place="weapon"),
    RuneDef("red_thirst", GEAR, "Красная жажда", 0.03, "{v} урона возвращается здоровьем", pvp="half",
            classes=(W,), place="weapon", ready=False),
    RuneDef("spite", GEAR, "Злоба", 0.02, "+{v} урона за каждый полученный удар, до пяти раз", pvp="half",
            classes=(W,), place="weapon", ready=False),
    RuneDef("thorn_plate", GEAR, "Колючая броня", 0.08, "{v} полученного урона уходит обратно врагу",
            pvp="half", classes=(W,), place="armor", ready=False),
    RuneDef("deaf_shield", GEAR, "Глухой щит", 0.06, "шанс {v} полностью блокировать обычную атаку",
            pvp="half", classes=(W,), place="armor", curve="tight", rarity="rare", ready=False),
    RuneDef("thin_sting", GEAR, "Тонкое жало", 0.12, "+{v} к урону крита", pvp="half",
            classes=(R,), place="weapon"),
    RuneDef("last_cut", GEAR, "Последний надрез", 0.12, "+{v} урона по целям ниже 30% здоровья", pvp="half",
            classes=(R,), place="weapon"),
    RuneDef("riposte", GEAR, "Ответный выпад", 0.20, "после уклонения следующий удар сильнее на {v}",
            pvp="half", classes=(R,), place="weapon"),
    RuneDef("rotten_wound", GEAR, "Гнилая рана", 0.20, "шанс {v}, что яд продержится на ход дольше",
            pvp="half", classes=(R,), place="weapon", curve="tight", rarity="rare", ready=False),
    RuneDef("light_step", GEAR, "Лёгкий шаг", 0.03, "+{v} к уклонению", pvp="half",
            classes=(R,), place="armor", curve="tight", rarity="rare"),
    RuneDef("echo", GEAR, "Отзвук", 0.08, "+{v} урона по целям под ослаблением, уязвимостью, ядом или горением",
            pvp="half", classes=(M,), place="weapon"),
    RuneDef("heat_frost", GEAR, "Жар и иней", 0.10, "горение и холод сильнее на {v}", pvp="half",
            classes=(M,), place="weapon", ready=False),
    RuneDef("surplus", GEAR, "Излишек", 0.20, "{v} лечения сверх максимума становится щитом", pvp="half",
            classes=(M,), place="armor"),
    RuneDef("reverse_prayer", GEAR, "Обратная молитва", 0.15, "{v} твоего лечения бьёт врага", pvp="half",
            classes=(M,), place="weapon", rarity="rare", ready=False),
    RuneDef("fresh_armor", GEAR, "Свежая броня", 0.15, "входящий урон в первые 3 хода меньше на {v}",
            pvp="half", place="armor"),
    RuneDef("cast_cuirass", GEAR, "Литая кираса", 0.25, "уязвимость на тебе слабее на {v}", place="armor"),
    RuneDef("not_today", GEAR, "Не сегодня", 0.05, "шанс {v} пережить смертельный удар, раз за бой",
            pvp="half", place="armor", curve="very_tight", rarity="mythic", ready=False),

    # --- Руны навыков -------------------------------------------------------------
    RuneDef("cold_count", SKILL, "Холодный счёт", 0.08, "шанс {v}, что навык не уйдёт в перезарядку",
            pvp="half", curve="tight", rarity="rare"),
    RuneDef("press", SKILL, "Нажим", 0.10, "навык бьёт сильнее на {v}", pvp="half"),
    RuneDef("blood_edge", SKILL, "Кровяная кромка", 0.05, "{v} урона навыка возвращается здоровьем",
            pvp="half", tag="damage", ready=False),
    RuneDef("ricochet", SKILL, "Отскок", 0.12, "в групповом бою шанс {v} задеть вторую цель с силой 40%",
            pvp="none", tag="damage", ready=False),
    RuneDef("grip", SKILL, "Хватка", 0.15, "+{v} к пробитию сопротивления контролю", pvp="half", tag="control", ready=False),
    RuneDef("acrid", SKILL, "Едкость", 0.15, "урон за ход от навыка сильнее на {v}", pvp="half", tag="dot", ready=False),
    RuneDef("viscous", SKILL, "Тягучесть", 0.25, "шанс {v}, что эффект навыка продержится на ход дольше",
            pvp="half", tag="duration", curve="tight", rarity="epic", ready=False),
    RuneDef("short_swing", SKILL, "Короткий взмах", 0.20, "шанс {v}, что перезарядка навыка на ход короче",
            pvp="half", tag="long_cd", curve="very_tight", rarity="mythic"),
    RuneDef("prop", SKILL, "Подпорка", 0.15, "лечение и щиты навыка сильнее на {v}", pvp="half",
            tag="heal_shield", ready=False),
]

BY_ID: dict[str, RuneDef] = {r.id: r for r in RUNES}

#: Навыки по типам для рун навыков. damage - любой навык с уроном
#: (multiplier > 0), long_cd - перезарядка от 4 ходов: оба считаются по
#: данным навыка. Остальное - вручную.
SKILL_TAG_TITLES = {
    "damage": "навыки с уроном", "control": "навыки контроля", "dot": "навыки с уроном за ход",
    "duration": "навыки с эффектом на несколько ходов", "long_cd": "навыки с перезарядкой от 4 ходов",
    "heal_shield": "лечение и щиты",
}
MANUAL_TAGS: dict[str, set[str]] = {
    "control": {"warrior_stagger", "mage_ice_bonds", "guardian_stonegrip", "elementalist_ice",
                "poisoner_disrupt"},
    "dot": {"poisoner_venom", "elementalist_fire", "poisoner_toxic_burst", "dark_mystic_drain"},
    "duration": {"warrior_warcry", "rogue_smoke", "mage_blood_seal", "guardian_block", "guardian_unbreakable",
                 "blood_knight_blood_seal", "shadow_blade_shadow_dance", "poisoner_decay", "elementalist_fire",
                 "dark_mystic_ward"},
    "heal_shield": {"guardian_block", "guardian_unbreakable", "dark_mystic_ward", "blood_knight_lifesteal_strike",
                    "dark_mystic_blood_pact", "dark_mystic_drain"},
}
