"""Рейд «Кукольный театр» (патч 53) — числовые константы. Не хардкодить в
сервисах/движке."""

RAID_PUPPET_THEATRE_ID = "puppet_theatre"
MONOLITH_COORDS = (0, 0)

# Пауза между этапами (текст патча) — HP восстанавливается всем целиком.
STAGE_TRANSITION_PAUSE_MIN_SECONDS = 5.0
STAGE_TRANSITION_PAUSE_MAX_SECONDS = 10.0

# --- Этап 1: Пробные куклы ---
STAGE1_MOB_COUNT = 3
STAGE1_MOB_HP = 8_000
STAGE1_LOOT_MULT = 2

# --- Этап 2: Семья Вельд ---
VELD_OSWALD = "veld_oswald"
VELD_IRMA = "veld_irma"
VELD_LITTA = "veld_litta"
# Порядок = ПРАВИЛЬНЫЙ порядок убийства.
VELD_ORDER: tuple[str, ...] = (VELD_OSWALD, VELD_IRMA, VELD_LITTA)
# Порядок ПОКАЗА - в выборе цели и на доске боя. Намеренно не совпадает с
# порядком убийства: при «1 - Освальд» первая же кнопка случайно оказывалась
# правильной, и загадка этапа решалась сама собой.
VELD_DISPLAY_ORDER: tuple[str, ...] = (VELD_IRMA, VELD_LITTA, VELD_OSWALD)
VELD_HP: dict[str, int] = {VELD_OSWALD: 14_000, VELD_IRMA: 9_000, VELD_LITTA: 6_000}
VELD_NAMES: dict[str, str] = {
    VELD_OSWALD: "Освальд Вельд", VELD_IRMA: "Ирма Вельд", VELD_LITTA: "Литта Вельд",
}
# Абсолютные (не накапливающиеся) множители к БАЗОВЫМ характеристикам
# оставшихся кукол — не ×2 поверх ×2, а замена на ×5 при второй ошибке.
VELD_FIRST_VIOLATION_MULT = 2.0
VELD_SECOND_VIOLATION_MULT = 5.0
STAGE2_LOOT_MULT = 3

# --- Этап 3: Хирург ---
SURGEON_NAME = "Хирург"
#: Уровень Хирурга для классовых испытаний («победи того, кто выше тебя»).
#: На 60 уровне в мире нет противников выше, и испытание было невыполнимо -
#: Хирург его закрывает. Опыт и лут считаются по обычному уровню босса.
SURGEON_TRIAL_LEVEL = 61
SURGEON_HP = 45_000
SURGEON_PHASE2_HP_THRESHOLD = 0.50
SURGEON_PHASE3_HP_THRESHOLD = 0.15
SURGEON_PHASE3_TURNS = 3          # ходов бездействия (2 эффекта + 1 подготовка)
SURGEON_PHASE3_DAMAGE_REQUIRED = 6_750

# Обычная ротация (по кругу): множитель к обычному удару (compute_hit).
SURGEON_RESECTION_MULT = 1.8
SURGEON_REPLACE_PARTS_MULT = 1.4
SURGEON_REPLACE_PARTS_WEAKEN = 0.25          # EffectKind.WEAKEN на цель
SURGEON_REPLACE_PARTS_WEAKEN_DURATION = 2
SURGEON_MATERIAL_WORK_MULT = 1.1             # бьёт ВСЕХ живых игроков
SURGEON_STITCH_PULL_MULT = 1.5
SURGEON_STITCH_PULL_LIFESTEAL = 0.30         # доля нанесённого урона — хил Хирургу

STAGE3_LOOT_MULT = 5

RAID_UNIQUE_ITEM_ID = "surgeon_scalpel"


# --- Предел этапа (решение владельца 2026-10-02) ---
# Этап, не взятый за столько ходов, кончается ультимативным ударом босса:
# гибнет вся группа. Это не навык из списка, а сценарный конец - чтобы рейд
# нельзя было «вытянуть» сотнями ходов на зельях.
RAID_STAGE_TURN_LIMIT = 200

RAID_ULTIMATE_TEXT = {
    "puppet_theatre": (
        "🎭 Занавес.\n\n"
        "Театру надоело ждать. Все нити под потолком натягиваются разом - и куклы, и хозяева, "
        "и сама сцена смыкаются над вами, как створки. Последнее, что слышно, - аплодисменты пустого зала.\n\n"
        "Спектакль окончен. Без вас."
    ),
    "graveless_field": (
        "⚔️ Генерал Тавр поднимает алебарду над головой.\n\n"
        "По этой команде встаёт всё поле - каждый, кто здесь когда-либо пал. Мертвецы идут единым строем, "
        "и строй проходит сквозь вас, не замедляя шага.\n\n"
        "Поле без могил получает новых солдат."
    ),
    "faceless_archive": (
        "📚 Архив закрывается.\n\n"
        "Полки сходятся, как страницы книги, и тишина становится тяжелее камня. Чернила стекают со стен "
        "и вписывают вас в каталог - без имён, без лиц.\n\n"
        "Отныне вы - карточки в чужом ящике."
    ),
}
