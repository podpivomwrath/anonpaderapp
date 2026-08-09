"""Числа системы маунтов (патч 25, п.7): скорость и риск нападения по
редкости. Каталог самих маунтов — content/mounts/mounts.json.

Пешком — SECONDS_PER_CELL_ON_FOOT (world_config.CELL_TRAVEL_SECONDS) без
риска нападения; обычный маунт по скорости ему РАВЕН — его ценность в
автоматическом перемещении к цели, а не в скорости самой по себе.
"""

# --- Пока не делать (патч 25): контент эпических/легендарных маунтов не
# добавлять — только структура редкостей ниже, чтобы движок был готов. ---

RARITY_SECONDS_PER_CELL = {
    "common": 10.0,
    "rare": 7.0,
    "epic": 5.0,
    "legendary": 2.5,
    # "admin" не используется для расчёта — путь фиксирован ADMIN_MOUNT_TRAVEL_SECONDS
    # целиком (см. services/mount_service.py::total_travel_seconds), это только
    # для мини-аппа, если он когда-нибудь захочет показать грубую ETA per-cell.
    "admin": 0.0,
}

RARITY_AMBUSH_CHANCE = {
    "common": 0.30,
    "rare": 0.20,
    "epic": 0.12,
    "legendary": 0.05,
    "admin": 0.0,  # патч 34, ч.3: «Пепельный вестник» — 0% нападение
}

RARITY_EMOJI = {
    "common": "⚪",
    "rare": "🔵",
    "epic": "🟠",
    "legendary": "🔴",
    "admin": "🛠",
}

RARITY_NAMES = {
    "common": "Обычный",
    "rare": "Редкий",
    "epic": "Эпический",
    "legendary": "Легендарный",
    "admin": "Служебный",
}

# Патч 34, ч.3: «Пепельный вестник» — ФИКСИРОВАННОЕ время НА ВЕСЬ путь
# (не за клетку), независимо от расстояния.
ADMIN_MOUNT_ID = "admin_ashen_herald"
ADMIN_MOUNT_TRAVEL_SECONDS = 3.0

# Как часто (в секундах) редактируется сообщение "в пути" на маунте с
# оставшимся временем — живой отсчёт, аналог respawn.py.
TRAVEL_COUNTDOWN_UPDATE_SECONDS = 15.0
