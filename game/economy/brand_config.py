"""Клеймо Хранителя - второй премиум, под высокие уровни (2026-11-06, решения
владельца). Покупается на любом уровне (владелец, 2026-11-06: без отвязки от 60).

Отдельно от Метки Хранителя (premium_config) и вместе с ней: Метка - для
прокачки, Клеймо - для тех, кому опыт уже не нужен. Силы в бою не даёт:
только добыча, удобство и объём. Проверка - premium_service.is_brand.
"""

BRAND_BADGE = "🌑"
BRAND_NAME = "Клеймо Хранителя"

#: Выпадение рун: исследование (rune_service.MOB_DROP_CHANCE) и кубики рун
#: хозяев этажей в руинах - шанс ×1,25.
RUNE_DROP_MULT = 1.25

#: Группа легла в руинах - носитель Клейма уносит эту долю реликвий из мешка
#: (руны сгорают, как у всех).
WIPE_KEEP_SHARE = 0.25

#: Ключи Монолита и слот пресета перенесены с Метки (2026-11-06). Метки,
#: активные в день переноса, держат их до конца срока (Character.legacy_perks_until).
#: Числа - raid_key_config.RAID_KEY_CAP_PREMIUM и premium_config.PRESET_SLOT_BONUS.

#: Обоз: лишний ящик в кузове каждой повозки.
CART_EXTRA_CRATES = 1

#: Долгое путешествие: шанс опыта ремесла за час ×2 (voyage_config.CRAFT_XP_CHANCE).
VOYAGE_CRAFT_CHANCE_MULT = 2.0

# Магазин: в полтора раза дороже Метки (premium_config.shop_price).
SHOP_MIN_DAYS = 1
SHOP_MAX_DAYS = 30
PRICE_MULT = 1.5

EXPIRY_WARNING_DAYS = 1
EXPIRY_WARNING_TEXT = f"{BRAND_BADGE} {BRAND_NAME} побледнеет завтра."
EXPIRED_TEXT = f"{BRAND_BADGE} {BRAND_NAME} сошло. Хранитель вычеркнул пометку на полях."


#: Набор «Метка и Клеймо» (2026-11-06): обе на один срок, скидка от суммы
#: цен по отдельности. Акция без срока - всегда первой в магазине.
PAIR_DISCOUNT = 0.20


def pair_full_price(days: int) -> int:
    from game.economy import premium_config as pc

    return pc.shop_price(days) + shop_price(days)


def pair_price(days: int) -> int:
    """Метка + Клеймо на days дней со скидкой, округлено до 5."""
    return round(pair_full_price(days) * (1 - PAIR_DISCOUNT) / 5) * 5


def shop_price(days: int) -> int:
    """Цена Клейма на days дней: цена Метки ×1,5, округлено до 5."""
    from game.economy import premium_config as pc

    return round(pc.shop_price(days) * PRICE_MULT / 5) * 5
