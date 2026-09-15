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
