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
HEAL_PCT = {
    "heal_small": 0.30,
    "heal_medium": 0.55,
    "heal_large": 1.0,
}

# --- Боевые эликсиры (бесплатное действие, лимит за бой) ---
ELIXIR_PER_BATTLE_LIMIT = 2

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
