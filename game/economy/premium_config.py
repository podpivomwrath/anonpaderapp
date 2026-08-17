"""Метка Хранителя — премиум-аккаунт (патч 50). Числа — сюда, не хардкодить.

Принципиально: премиум НЕ даёт силовых преимуществ (статы/урон/HP/PvP) —
только скорость, удобство, объём. Не продаётся нигде — только промокодом
администратора (services/promo_service.py). Единая проверка активности —
services/premium_service.py::is_premium.
"""

PREMIUM_BADGE = "💠"
PREMIUM_NAME = "Метка Хранителя"

# 1. Опыт — все источники (единая точка: services/experience_service.py::add_experience)
PREMIUM_XP_MULTIPLIER = 1.5

# 2. Редкость лута — шанс поднять на одну ступень ПОСЛЕ определения базовой
# редкости, один раз, не каскадом. Легендарная — потолок (см. game/economy/item_gen.py).
PREMIUM_RARITY_UPGRADE_CHANCE = 0.30

# 3. Лимит ключей рейда — значение живёт в game/economy/raid_key_config.py
# (RAID_KEY_CAP_PREMIUM, рядом с базовым RAID_KEY_CAP), не дублируется здесь.
# Никогда не отбирать уже полученные ключи при истечении — только не выдавать
# новые сверх (уже неактивного) лимита, см. services/raid_key_service.py.

# 4. Слоты пресетов — бонус СВЕРХ купленных (character.preset_slots), не
# отбирается при истечении — просто недоступен для переключения/сохранения
# сверх эффективного лимита (services/preset_service.py::effective_preset_slots).
PRESET_SLOT_BONUS = 1

# 5. Отдых — [min, max] сек вместо game.world.world_config.REST_SECONDS_MIN/MAX.
REST_SECONDS_MIN = 4.0
REST_SECONDS_MAX = 6.0

# 6. Ежедневные задания — значение живёт в game/economy/dailies_config.py
# (DAILY_QUEST_COUNT_PREMIUM, рядом с базовым DAILY_QUEST_COUNT).

# Уведомления об истечении (services/premium_service.py) — за сколько до
# конца срока предупреждать; идемпотентность — character.premium_warn_sent/
# premium_expire_notified, сбрасываются при каждом продлении.
EXPIRY_WARNING_DAYS = 1
EXPIRY_WARNING_TEXT = f"{PREMIUM_BADGE} {PREMIUM_NAME} потускнеет завтра."
EXPIRED_TEXT = f"{PREMIUM_BADGE} {PREMIUM_NAME} погасла. Хранитель снова смотрит на тебя как на всех."

# Допустимые длительности активации промокодом (Часть 2) — дни.
ALLOWED_DURATIONS_DAYS = (3, 7, 30)
