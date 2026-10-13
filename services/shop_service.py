"""Магазин мини-аппа (2026-10-13): товары за самоцветы.

Пока товар один - Метка Хранителя на 1-30 дней (premium_config.shop_price).
Каталог отдаётся целиком с ценами на каждый срок: ползунок на фронтенде
показывает цену сразу, а сервер при покупке считает её заново - цене с
клиента не верим.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import dailies_config as dc
from game.economy import premium_config as pc
from game.economy import raid_key_config as rkc
from game.world import world_config as wc
from models import Character
from services import premium_service, wallet_service

PREMIUM_ID = "premium"


class ShopError(Exception):
    pass


def _premium_perks() -> list[str]:
    return [
        f"+{round((pc.PREMIUM_XP_MULTIPLIER - 1) * 100)}% опыта из всех источников",
        f"{round(pc.PREMIUM_RARITY_UPGRADE_CHANCE * 100)}% шанс поднять редкость выпавшей вещи на ступень",
        f"ежедневных заданий {dc.DAILY_QUEST_COUNT_PREMIUM} вместо {dc.DAILY_QUEST_COUNT}",
        f"Ключей Монолита до {rkc.RAID_KEY_CAP_PREMIUM} вместо {rkc.RAID_KEY_CAP}",
        f"+{pc.PRESET_SLOT_BONUS} слот пресета",
        f"отдых {round(pc.REST_SECONDS_MIN)}-{round(pc.REST_SECONDS_MAX)} с вместо "
        f"{round(wc.REST_SECONDS_MIN)}-{round(wc.REST_SECONDS_MAX)}",
        f"{pc.PREMIUM_BADGE} у ника",
    ]


def catalog(character: Character, gems: int) -> dict:
    until = character.premium_until
    active = premium_service.is_premium(character)
    return {
        "gems": gems,
        "items": [{
            "id": PREMIUM_ID,
            "title": pc.PREMIUM_NAME,
            "emoji": pc.PREMIUM_BADGE,
            "kind": "days",
            "min": pc.SHOP_MIN_DAYS,
            "max": pc.SHOP_MAX_DAYS,
            "prices": {d: pc.shop_price(d) for d in range(pc.SHOP_MIN_DAYS, pc.SHOP_MAX_DAYS + 1)},
            "perks": _premium_perks(),
            "note": "Без силовых преимуществ: статы, урон и HP не меняются. Срок складывается с оставшимся.",
            "active_until": until.isoformat() if active and until is not None else None,
        }],
    }


async def buy_premium(db: AsyncSession, character: Character, days: int) -> datetime:
    """Списать самоцветы и продлить Метку. Возвращает новый срок."""
    if not isinstance(days, int) or not pc.SHOP_MIN_DAYS <= days <= pc.SHOP_MAX_DAYS:
        raise ShopError(f"Срок - от {pc.SHOP_MIN_DAYS} до {pc.SHOP_MAX_DAYS} дней.")
    price = pc.shop_price(days)
    try:
        await wallet_service.charge(db, character.id, "donate", price)
    except wallet_service.NotEnoughCurrency:
        raise ShopError(f"Не хватает самоцветов: нужно 💎{price}.") from None
    premium_service.extend(character, days, datetime.now(timezone.utc))
    await db.flush()
    return character.premium_until
