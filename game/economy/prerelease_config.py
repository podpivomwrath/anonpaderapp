"""Дар первопроходцев (2026-10-29, владелец): все дорелизные поблажки - в
одном месте, как бессрочный бафф каждого игрока. Он виден во вкладке «Герой»
со списком бонусов.

Код игры числа отсюда берёт через функции ниже и про тест не знает: к
релизу ACTIVE = False - и всё работает так, как задумано на самом деле.
Новая дорелизная поблажка добавляется сюда же, строкой в BONUSES.
"""

ACTIVE = True
TITLE = "Дар первопроходцев"
EMOJI = "🌱"
ABOUT = "Пока мир не открыт для всех, тем, кто пришёл первым, многое даётся легче."

ORE_SPAWN_MULT = 2.0     # руда в рудниках появляется чаще
MINING_XP_MULT = 2.0     # опыт горного дела
GUILD_FAME_MULT = 2.0    # слава гильдии - её уровень
FREE_RESPEC = True       # переделка у Хранителя Списков: класс, подкласс, характеристики
FREE_PATH_REPICK = True  # новый путь после смены класса или подкласса
ARENA_FREE_ELIXIRS = True  # на арене все зелья, эликсиры и свитки - бесплатно, без сумки
RESPAWN_MULT = 0.5       # воскрешение вдвое быстрее (2026-10-30, владелец)

#: Что показать игроку в «Герое»: (включено ли, строка).
BONUSES = (
    (FREE_RESPEC, "Хранитель Списков меняет класс, подкласс и характеристики бесплатно"),
    (FREE_PATH_REPICK, "Новый путь после смены класса или подкласса - без платы"),
    (MINING_XP_MULT > 1, f"Горное дело: опыт ×{MINING_XP_MULT:g}"),
    (ORE_SPAWN_MULT > 1, f"Руда в рудниках появляется в {ORE_SPAWN_MULT:g} раза чаще"),
    (GUILD_FAME_MULT > 1, f"Слава гильдии растёт ×{GUILD_FAME_MULT:g}"),
    (ARENA_FREE_ELIXIRS, "Арена: любые зелья, эликсиры и свитки бесплатно, сумка не тратится"),
    (RESPAWN_MULT < 1, f"Воскрешение в {1 / RESPAWN_MULT:g} раза быстрее"),
)


def ore_spawn_mult() -> float:
    return ORE_SPAWN_MULT if ACTIVE else 1.0


def mining_xp_mult() -> float:
    return MINING_XP_MULT if ACTIVE else 1.0


def guild_fame_mult() -> float:
    return GUILD_FAME_MULT if ACTIVE else 1.0


def free_respec() -> bool:
    return ACTIVE and FREE_RESPEC


def free_path_repick() -> bool:
    return ACTIVE and FREE_PATH_REPICK


def respawn_mult() -> float:
    return RESPAWN_MULT if ACTIVE else 1.0


def arena_free_elixirs() -> bool:
    return ACTIVE and ARENA_FREE_ELIXIRS


def card() -> dict | None:
    """Карточка для «Героя»; None - даров нет."""
    if not ACTIVE:
        return None
    return {"title": TITLE, "emoji": EMOJI, "about": ABOUT, "lines": [text for on, text in BONUSES if on]}
