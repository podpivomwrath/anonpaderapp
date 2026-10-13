"""Числовые значения зелий и эликсиров (патч 16): цены, проценты, длительности.

Каталог (id/название/эмодзи/описание) — в content/items/elixirs.json.
"""

ELIXIR_PRICES = {
    "heal_small": 40,
    "heal_medium": 120,
    "heal_large": 350,
    "ashen_fever": 150,
    "blood_for_blood": 150,
    "ashen_haze": 180,
    "shard_blood": 200,
    "blood_clarity": 220,
    "second_heart": 250,
    "last_breath": 300,
}

# --- Лечебные зелья (тратят ход в бою, вне боя — мгновенно) ---
# Лечение = фикс + доля максимального здоровья (2026-10-13, решение
# владельца): было 30/55/100% - Большое лечило полностью, и 10 зелий за бой
# давали десять запасов здоровья. Фикс держит зелья заметными у новичков,
# малая доля режет лечение на высоких уровнях в 3-5 раз.
HEAL_FORMULA: dict[str, tuple[int, float]] = {
    "heal_small": (50, 0.08),
    "heal_medium": (100, 0.12),
    "heal_large": (200, 0.15),
}


# Лечебные зелья в добыче с мобов (2026-10-13, решение владельца): иногда,
# и чем ближе к Монолиту - тем крупнее. Кольцо - по клетке боя: 1 - внешнее
# (старт), 5 - центр. Вес: (малое, среднее, большое).
HEAL_DROP_CHANCE = 0.06
HEAL_DROP_BY_RING: dict[int, tuple[int, int, int]] = {
    1: (85, 15, 0),
    2: (55, 40, 5),
    3: (25, 55, 20),
    4: (10, 45, 45),
    5: (0, 30, 70),
}
HEAL_IDS = ("heal_small", "heal_medium", "heal_large")


def heal_amount(item_id: str | None, max_hp: int) -> int | None:
    """Сколько лечит зелье бойцу с max_hp; None - это не лечебное зелье."""
    formula = HEAL_FORMULA.get(item_id) if item_id else None
    if formula is None:
        return None
    flat, pct = formula
    return round(flat + max_hp * pct)

# --- Боевые эликсиры (бесплатное действие, лимит за бой) ---
ELIXIR_PER_BATTLE_LIMIT = 2

# 📜 Свитки (2026-10-13) - только из Ларца расходников кровавого разлома, в
# лавке их нет. В бою - как боевой эликсир (тот же лимит), но на всю сторону.
SCROLL_HEAL_PCT = 0.30          # Свиток лечения: каждому союзнику % его здоровья
SCROLL_WARD_PCT = 0.30          # Свиток оберега: щит % здоровья получателя
SCROLL_WARD_DURATION = 2
SCROLL_VULNERABILITY = 0.35     # Свиток уязвимости: +35% входящего урона врагам
SCROLL_VULNERABILITY_DURATION = 2

# Всего расходников за один бой - лечебные зелья и боевые эликсиры вместе
# (решение владельца 2026-10-02: одиночка вытягивал рейд на 70 зельях за этап).
# Этап рейда - отдельный бой.
CONSUMABLES_PER_BATTLE = 10

# --- Лавка (патч 39, ч.4): кнопки количества при покупке ---
SHOP_BULK_QUANTITIES = [1, 5, 10, 25]

# 🔥 Пепельная лихорадка
ASHEN_FEVER_DURATION = 3
ASHEN_FEVER_DAMAGE_BONUS_STEP = 0.10  # +10% на 1-й ход, +20% на 2-й, +30% на 3-й
ASHEN_FEVER_SELF_DAMAGE_PCT_MAX_HP = 0.05

# 💀 Последний вздох
LAST_BREATH_DURATION = 3

# 🩸 Кровь за кровь
BLOOD_FOR_BLOOD_DURATION = 2
BLOOD_FOR_BLOOD_REFLECT_PCT = 0.30

# 🧿 Ясность крови
BLOOD_CLARITY_DURATION = 2

# 🛡️ Второе сердце — щит % от макс. HP; TODO: калибровка (патч не дал точного числа)
SECOND_HEART_DURATION = 3
SECOND_HEART_SHIELD_PCT_MAX_HP = 0.30

# 🌫️ Пепельный морок
ASHEN_HAZE_DURATION = 2
ASHEN_HAZE_DODGE_CHANCE = 0.80

# ⚡ Осколочная кровь — фикс. бонус урона за удар = уровень * коэф.; TODO: калибровка
SHARD_BLOOD_DURATION = 3
SHARD_BLOOD_DAMAGE_PER_LEVEL = 1.5
