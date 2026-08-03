"""Числовые значения ежедневных заданий, стриков и наград за вход (патч 23).

Пул заданий (каталог id/title/условие) — в content/quests/dailies.json.
"""

DAILY_RESET_TZ = "Europe/Moscow"

DAILY_QUEST_COUNT = 3

# Задания на PvP не выпадают игрокам ниже этого уровня (патч 23, п.3).
PVP_QUEST_MIN_LEVEL = 15

# --- Масштабирование цели по уровню игрока ---
# target = round(base_target * (1 + (level - 1) * TARGET_LEVEL_SCALE)), но не меньше base_target.
TARGET_LEVEL_SCALE = 0.03


def scaled_target(base_target: int, level: int) -> int:
    return max(base_target, round(base_target * (1 + (level - 1) * TARGET_LEVEL_SCALE)))


# --- Награда за одно выполненное задание (опыт + золото), масштабируется по
# уровню — ежедневки не должны быть выгоднее обычного фарма (патч 23, п.3):
# опыт — небольшая доля от xp_per_mob(level) за одно задание, а не за килл.
DAILY_XP_MOB_FRACTION = 0.5
DAILY_GOLD_BASE = 30
DAILY_GOLD_PER_LEVEL = 6


def daily_reward(level: int) -> tuple[int, int]:
    """(xp, gold) за одно выполненное ежедневное задание."""
    from services.experience_service import xp_per_mob

    xp = round(xp_per_mob(level) * DAILY_XP_MOB_FRACTION)
    gold = DAILY_GOLD_BASE + DAILY_GOLD_PER_LEVEL * level
    return xp, gold


# --- Рубежи стрика ежедневок (патч 23, п.4) ---
# Каждый рубеж: gold/gems — фикс. числа; elixirs_random_combat — N случайных
# БОЕВЫХ (category=="combat") эликсиров по 2 шт. каждого; title — id титула
# из content/quests/dailies.json-соседнего каталога (пока хардкод здесь,
# единственный титул в игре).
STREAK_MILESTONES: dict[int, dict] = {
    7: {"gold": 2000, "elixirs_random_combat": 2},
    14: {"gems": 25},
    28: {"gold": 5000, "gems": 50},
    56: {"gems": 100},
    112: {"gems": 200},
    224: {"gems": 400},
    365: {"gems": 1000, "title": "relentless"},
}

TITLE_NAMES = {
    "relentless": "Неотступный",
}

# --- Награды 14-дневного цикла входа (патч 23, п.5) ---
# elixir — (elixir_id, count); gold — золото.
LOGIN_CYCLE_LENGTH = 14
LOGIN_CYCLE_REWARDS: dict[int, dict] = {
    1: {"elixir": ("heal_small", 3)},
    2: {"gold": 500},
    3: {"elixir": ("heal_small", 5)},
    4: {"elixir": ("ashen_haze", 1)},
    5: {"elixir": ("heal_medium", 3)},
    6: {"gold": 1000},
    7: {"elixir": ("second_heart", 2)},
    8: {"elixir": ("heal_medium", 5)},
    9: {"gold": 1500},
    10: {"elixir": ("shard_blood", 2)},
    11: {"elixir": ("heal_large", 2)},
    12: {"gold": 2000},
    13: {"elixir": ("last_breath", 2)},
    14: {"gems": 50},
}

# Пул эликсиров категории "combat" для STREAK_MILESTONES[7]["elixirs_random_combat"]
COMBAT_ELIXIR_POOL = [
    "ashen_fever", "last_breath", "blood_for_blood", "blood_clarity",
    "second_heart", "ashen_haze", "shard_blood",
]
