"""Числа гильдий: основание, звания, слава и уровни, территория, постройки,
осады, сезоны, гильдейский босс. Не хардкодить по сервисам.

Масштаб золота. Ежедневка на 60 уровне даёт ~400 золота, активный игрок
шестидесятого уровня зарабатывает за вечер несколько тысяч. Поэтому всё,
что покупает ГИЛЬДИЯ (знамя, осада, постройки, древо), стоит десятки и сотни
тысяч: такое собирается казной всей гильдии, а не одним игроком. Личная
молитва в часовне стоит 1000 - это заметно, но по карману одному.
"""

# --- Основание ---------------------------------------------------------------
#: Самоцветы, не золото: основание должно быть решением, а не прихотью.
FOUND_COST_GEMS = 1000
FOUND_MIN_LEVEL = 20
#: Вкладка гильдий и вступление - с этого уровня.
JOIN_MIN_LEVEL = 20
NAME_MIN_LEN = 3
NAME_MAX_LEN = 24
TAG_MIN_LEN = 2
TAG_MAX_LEN = 4

#: Защита от прыжков: вышедший (или исключённый) не может вступить никуда
#: сутки. Иначе сильного игрока «одалживали» бы на осаду и возвращали.
REJOIN_COOLDOWN_HOURS = 24
INVITE_TTL_HOURS = 48

# --- Звания ------------------------------------------------------------------
RANK_LEADER = "leader"
RANK_TREASURER = "treasurer"
RANK_OFFICER = "officer"
RANK_VETERAN = "veteran"
RANK_RECRUIT = "recruit"
#: Старшинство: больше - выше.
RANK_ORDER = {
    RANK_RECRUIT: 0, RANK_VETERAN: 1, RANK_OFFICER: 2, RANK_TREASURER: 3, RANK_LEADER: 4,
}
RANK_TITLES = {
    RANK_LEADER: "Глава",
    RANK_TREASURER: "Казначей",
    RANK_OFFICER: "Офицер",
    RANK_VETERAN: "Ветеран",
    RANK_RECRUIT: "Рядовой",
}

# --- Состав ------------------------------------------------------------------
MEMBERS_BASE = 30
MEMBERS_MAX = 50


def member_cap(level: int) -> int:
    """30 на первом уровне, +1 за уровень, потолок 50 (на 21-м)."""
    return min(MEMBERS_BASE + (level - 1), MEMBERS_MAX)


# --- Слава и уровни ----------------------------------------------------------
# Уровень бесконечен, каждый следующий дороже. Каждый уровень даёт одно очко
# древа. Древо целиком (237 очков) открывается на ~238 уровне: при активной
# гильдии 1500 славы в день это годы, как и задумано.


def fame_to_next(level: int) -> int:
    return round(80 * level + 0.2 * level ** 2)


TREE_POINTS_PER_LEVEL = 1

# --- Гильдейские ежедневки и недельные задания -------------------------------
DAILIES_PER_MEMBER = 2
DAILY_FAME = 10
DAILY_CONTRIBUTION = 10
#: Сколько золота сверху получает сам игрок за гильдейскую ежедневку.
DAILY_PERSONAL_GOLD = 150

WEEKLY_QUESTS = 5
WEEKLY_FAME = 300

#: Пул целей: metric -> (заголовок, подпись прогресса, база личной цели,
#: база общей цели НА ОДНОГО участника). Общая цель недели = база * число
#: участников (не меньше 5): в гильдии из 40 человек и цель больше.
QUEST_METRICS: dict[str, tuple[str, str, int, int]] = {
    "kill": ("Истребление", "Убить врагов", 25, 60),
    "explore": ("Разведка", "Провести исследования", 12, 30),
    "event": ("Дела земли", "Пройти события с выбором", 6, 12),
    "cells": ("Дозор", "Пройти клетки карты", 40, 80),
    "trophies": ("Добытчики", "Собрать трофеи", 20, 50),
    "sell_gold": ("Торг", "Выручить золота у скупщика", 2500, 5000),
    "pvp_win": ("Кровь за кровь", "Победить в PvP", 2, 3),
    "ore": ("Кайло и порода", "Добыть руду", 3, 6),
    "fish": ("Улов", "Поймать рыбу", 6, 12),
}
WEEKLY_MIN_MEMBERS_FOR_TARGET = 5

# --- Казна и склад -----------------------------------------------------------
#: Меньше в казну не вносят: журнал не должен тонуть во взносах по монете.
DEPOSIT_MIN_GOLD = 100
DEPOSIT_MIN_GEMS = 10
#: Налог гильдии на золото участников: от 0 до 50%.
TAX_MAX = 50
# Казна - золото и самоцветы. Склад - руда и снаряжение. Реликвии (трофеи)
# на склад не кладутся: это товар скупщика, а не ресурс гильдии.
WAREHOUSE_BASE_ORE = 500
WAREHOUSE_BASE_ITEMS = 10
WAREHOUSE_ORE_PER_LEVEL = 250
WAREHOUSE_ITEMS_PER_LEVEL = 5

# --- Территория --------------------------------------------------------------
#: Захватывать можно кольца 2-4 (тиры карты 2..4). Внешнее кольцо - зона
#: новичков, центр - Монолит: туда нельзя никогда. Озёра - нельзя.
CLAIMABLE_RING_TIERS = (2, 3, 4)

#: Слоты обычных клеток по уровню гильдии: (уровень, слотов).
CELL_SLOTS = [(3, 1), (8, 2), (15, 3), (25, 4), (40, 5)]
#: Слот рудника - один, с этого уровня.
MINE_SLOT_LEVEL = 20


def cell_slots(level: int) -> int:
    slots = 0
    for need, value in CELL_SLOTS:
        if level >= need:
            slots = value
    return slots


def mine_slots(level: int) -> int:
    return 1 if level >= MINE_SLOT_LEVEL else 0


#: Знамя: золото из казны. Каждое следующее дороже - чтобы держать много
#: клеток было делом всей гильдии.
BANNER_COST_CELL = 100_000
BANNER_COST_MINE = 300_000
BANNER_COST_PER_HELD = 0.5   # +50% за каждую уже занятую клетку


def banner_cost(is_mine: bool, held: int) -> int:
    base = BANNER_COST_MINE if is_mine else BANNER_COST_CELL
    return round(base * (1 + BANNER_COST_PER_HELD * held))


#: Закладка: руда со склада (вид по кольцу, любая градация) и исследования
#: клетки участниками гильдии.
CLAIM_ORE: dict[int, tuple[str, int]] = {
    2: ("salt_quartz", 15),
    3: ("taint_pyrite", 15),
    4: ("ashen_silver", 15),
}
CLAIM_ORE_MINE_MULT = 2
CLAIM_EXPLORATIONS = 40
CLAIM_HOURS = 48

#: Десятина: каждое исследование на клетке гильдии (кем угодно) приносит
#: казне золото. Деньги чеканятся, у исследователя ничего не отнимается.
TITHE_BY_RING = {2: 20, 3: 40, 4: 60}

# --- Базы --------------------------------------------------------------------
BASE_OUTPOST = "outpost"
BASE_FORT = "fort"
BASE_CITADEL = "citadel"
BASE_ORDER = [BASE_OUTPOST, BASE_FORT, BASE_CITADEL]
BASE_TITLES = {BASE_OUTPOST: "Застава", BASE_FORT: "Форт", BASE_CITADEL: "Цитадель"}
BASE_SLOTS = {BASE_OUTPOST: 2, BASE_FORT: 4, BASE_CITADEL: 6}
#: Потолок уровня построек на базе этой ступени.
BASE_BUILDING_MAX = {BASE_OUTPOST: 3, BASE_FORT: 6, BASE_CITADEL: 10}
#: Уровень гильдии, с которого доступна ступень.
BASE_UNLOCK_LEVEL = {BASE_OUTPOST: 1, BASE_FORT: 10, BASE_CITADEL: 30}
#: Цена подъёма до ступени: (золото, (руда, штук), часов стройки).
BASE_UPGRADE_COST = {
    BASE_FORT: (250_000, ("ashen_silver", 40), 12),
    BASE_CITADEL: (1_000_000, ("crimson_cluster", 60), 48),
}

# --- Постройки ---------------------------------------------------------------
B_BARRACKS = "barracks"
B_TOWER = "tower"
B_CHAPEL = "chapel"
B_FORGE = "forge"
B_SHAFT = "shaft"
B_TOTEM = "totem"
B_WAREHOUSE = "warehouse"
B_GATES = "gates"
BUILDINGS = [B_BARRACKS, B_TOWER, B_CHAPEL, B_FORGE, B_SHAFT, B_TOTEM, B_WAREHOUSE, B_GATES]
BUILDING_TITLES = {
    B_BARRACKS: "Казармы",
    B_TOWER: "Сторожевая башня",
    B_CHAPEL: "Часовня",
    B_FORGE: "Кузня",
    B_SHAFT: "Шахта",
    B_TOTEM: "Тотем",
    B_WAREHOUSE: "Склад",
    B_GATES: "Врата",
}
BUILDING_EMOJI = {
    B_BARRACKS: "🛡", B_TOWER: "🗼", B_CHAPEL: "⛪", B_FORGE: "⚒",
    B_SHAFT: "⛏", B_TOTEM: "🗿", B_WAREHOUSE: "📦", B_GATES: "🌀",
}
#: Шахта - только на клетке рудника и только три уровня.
SHAFT_MAX_LEVEL = 3
#: Базовая цена первого уровня в золоте; уровень L стоит base * L^1.5.
BUILDING_BASE_GOLD = {
    B_BARRACKS: 20_000, B_TOWER: 20_000, B_CHAPEL: 25_000, B_FORGE: 30_000,
    B_SHAFT: 60_000, B_TOTEM: 30_000, B_WAREHOUSE: 15_000, B_GATES: 40_000,
}
#: Руда на подъём: вид по уровню постройки, штук = BUILD_ORE_PER_LEVEL * L.
BUILD_ORE_BY_LEVEL = [
    (1, "salt_quartz"), (4, "taint_pyrite"), (7, "ashen_silver"), (9, "crimson_cluster"),
]
BUILD_ORE_PER_LEVEL = 4
#: Часов стройки = BUILD_HOURS_PER_LEVEL * L.
BUILD_HOURS_PER_LEVEL = 1.0


def build_gold(building: str, level: int) -> int:
    return round(BUILDING_BASE_GOLD[building] * level ** 1.5)


def build_ore(level: int) -> tuple[str, int]:
    ore_id = BUILD_ORE_BY_LEVEL[0][1]
    for need, value in BUILD_ORE_BY_LEVEL:
        if level >= need:
            ore_id = value
    return ore_id, BUILD_ORE_PER_LEVEL * level


def build_hours(level: int) -> float:
    return BUILD_HOURS_PER_LEVEL * level


# Казармы: гарнизон защищает ЭТУ базу при осаде.
def garrison_size(level: int) -> int:
    return 0 if level <= 0 else 1 + level // 3


GARRISON_LEVEL = 60
GARRISON_POWER_PER_LEVEL = 0.12   # +12% к статам гарнизона за уровень казарм
GARRISON_BASE_STAT = 70           # статы одного стража на 1 уровне казарм

# Башня: предупреждение о чужих на клетке и усиление гарнизона в осаде.
TOWER_GARRISON_PER_LEVEL = 0.04
TOWER_WARN_COOLDOWN_MINUTES = 10

# Часовня: точка возрождения, ускоренный респаун, молитва.
CHAPEL_RESPAWN_CUT_PER_LEVEL = 0.03
PRAYER_BASE_COST = 1000
PRAYER_CUT_PER_LEVEL = 50          # 1000 -> 500 на 10 уровне
PRAYER_STAT_BONUS = 0.10
PRAYER_MINUTES = 60
PRAYER_MIN_COST = 300

# Кузня: дешевле руда в мастерской для всех участников.
FORGE_ORE_CUT_PER_LEVEL = 0.02

# Шахта: доля скорости игрока, руда сразу на склад.
SHAFT_RATE = {1: 0.10, 2: 0.25, 3: 0.50}
#: «Скорость игрока» - одна руда за столько секунд (середина 5-15 минут).
SHAFT_PLAYER_SECONDS = 600.0
#: Уровень горного дела, с которым копает шахта (для градации руды).
SHAFT_MINING_LEVEL = 40

# Тотем: аура 3x3 вокруг базы.
TOTEM_DOUBLE_DROP_PER_LEVEL = 0.01
TOTEM_STAT_BONUS_LEVEL = 9          # с этого уровня +5% ко всем статам
TOTEM_STAT_BONUS = 0.05
TOTEM_RADIUS = 1                    # 3x3

# Врата: перемещение между своими базами с вратами.
GATES_COOLDOWN_MINUTES = 15
GATES_COOLDOWN_CUT_PER_LEVEL = 1

# --- Осады -------------------------------------------------------------------
SIEGE_COST = {BASE_OUTPOST: 50_000, BASE_FORT: 100_000, BASE_CITADEL: 200_000}
#: Осада начинается в ближайшее окно защитников, но не раньше чем через
#: столько часов после объявления: защитникам нужно время собраться.
SIEGE_MIN_NOTICE_HOURS = 12
#: За час до начала драться на клетке нельзя: люди собираются.
SIEGE_GATHER_MINUTES = 60
DEFAULT_SIEGE_HOUR = 20          # 20:00 МСК
SIEGE_HOURS_ALLOWED = range(12, 24)
CAPTURE_SHIELD_HOURS = 48
DEFENSE_SHIELD_HOURS = 24
#: Добыча с казны проигравшего: доля золота, склад её срезает.
SIEGE_LOOT_SHARE = 0.10
SIEGE_LOOT_CUT_PER_WAREHOUSE_LEVEL = 0.008

# --- Сезоны ------------------------------------------------------------------
#: Очки сезона за сутки владения (снимок раз в сутки).
SEASON_POINTS_CELL = 1
SEASON_POINTS_MINE = 2
SEASON_POINTS_CITADEL = 3
#: Слава этого месяца тоже идёт в зачёт - по очку за столько славы.
SEASON_FAME_PER_POINT = 100
SEASON_TITLE_ID = "season_lords"
SEASON_GEMS_TO_TREASURY = 500

# --- Гильдейский босс («Страж цитадели») -------------------------------------
BOSS_SUMMON_GOLD = 200_000
BOSS_SUMMON_ORE = ("ashen_silver", 30)
BOSS_COOLDOWN_DAYS = 7
BOSS_LIFETIME_HOURS = 24
BOSS_HP_PER_MEMBER = 6000
BOSS_MIN_HP = 60_000
BOSS_ATTEMPT_TURNS = 10
BOSS_ATTEMPT_COOLDOWN_MINUTES = 60
BOSS_FAME = 600
BOSS_TREASURY_GOLD = 150_000
BOSS_PERSONAL_GOLD = 3000      # делится по урону между участниками (x число бойцов)
BOSS_ORE_REWARD = ("crimson_cluster", 10)

# --- Древо -------------------------------------------------------------------
TREE_GOLD_SMALL = 10_000
TREE_GOLD_NOTABLE = 40_000
TREE_GOLD_KEYSTONE = 150_000
#: Каждый уже взятый узел удорожает следующие на 3%.
TREE_GOLD_GROWTH = 0.03
#: Сброс древа: возвращаются очки, золото - нет; сам сброс стоит самоцветов.
TREE_RESET_GEMS = 300
