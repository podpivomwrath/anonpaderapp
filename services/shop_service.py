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


def catalog(character: Character, gems: int, firm_name: str | None = None) -> dict:
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
        }, *rename_items(character, firm_name)],
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


# --- Смена ника и названия фирмы (2026-10-16, решение владельца) ---
# Самоцветы списываются в момент подтверждения вместе со сменой: если имя не
# подходит (занято, мат, неверные символы), ничего не списывается.

RENAME_ID = "rename"
FIRM_RENAME_ID = "firm_rename"
RENAME_PRICE = 300
FIRM_RENAME_PRICE = 500


def rename_items(character: Character, firm_name: str | None) -> list[dict]:
    from game.economy import trade_config as tc

    return [
        {
            "id": RENAME_ID, "title": "Смена ника", "emoji": "✏️", "kind": "rename", "price": RENAME_PRICE,
            "current": character.name, "min_len": 3, "max_len": 16,
            "rules": "3-16 символов: русские или латинские буквы, цифры и _. Ник должен быть свободен.",
        },
        {
            "id": FIRM_RENAME_ID, "title": "Смена названия фирмы", "emoji": "🏛", "kind": "rename",
            "price": FIRM_RENAME_PRICE, "current": firm_name, "available": firm_name is not None,
            "unavailable": "Сначала открой торговую фирму и дай ей название.",
            "min_len": tc.FIRM_NAME_MIN, "max_len": tc.FIRM_NAME_MAX,
            "rules": f"{tc.FIRM_NAME_MIN}-{tc.FIRM_NAME_MAX} символов: буквы, цифры, пробел и дефис. "
                     "Название должно быть свободно.",
        },
    ]


_NICK_ERRORS = {
    "invalid": "Ник - 3-16 символов: русские или латинские буквы, цифры и _.",
    "banned": "Такой ник не пройдёт - выбери другой.",
    "taken": "Этот ник уже занят.",
}


async def _charge(db: AsyncSession, character: Character, price: int) -> None:
    try:
        await wallet_service.charge(db, character.id, "donate", price)
    except wallet_service.NotEnoughCurrency:
        raise ShopError(f"Не хватает самоцветов: нужно 💎{price}.") from None


async def rename_character(db: AsyncSession, character: Character, new_name) -> str:
    from services import onboarding_service

    name = new_name.strip() if isinstance(new_name, str) else ""
    if name == character.name:
        raise ShopError("Это и так твой ник.")
    error = onboarding_service.validate_nickname_format(name)
    if error is None and onboarding_service.contains_banned_word(name):
        error = "banned"
    if error is None and await onboarding_service.is_nickname_taken(db, name, exclude_character_id=character.id):
        error = "taken"
    if error is not None:
        raise ShopError(_NICK_ERRORS[error])
    await _charge(db, character, RENAME_PRICE)
    old = character.name
    character.name = name
    await db.flush()
    from services import admin_service

    await admin_service.log_action(
        db, 0, "shop_rename", character.id, old_value={"name": old}, new_value={"name": name},
    )
    return old


async def rename_firm(db: AsyncSession, character: Character, new_name) -> str:
    from services import trade_service

    firm = await trade_service.get_firm(db, character.id, lock=True)
    if firm is None or not firm.name:
        raise ShopError("Сначала открой торговую фирму и дай ей название.")
    if isinstance(new_name, str) and trade_service.clean_name(new_name) == firm.name:
        raise ShopError("Фирма и так так называется.")
    try:
        name = await trade_service._check_name(db, new_name)
    except trade_service.TradeError as exc:
        raise ShopError(str(exc)) from None
    await _charge(db, character, FIRM_RENAME_PRICE)
    old = firm.name
    firm.name, firm.name_key = name, name.lower()
    await db.flush()
    from services import admin_service

    await admin_service.log_action(
        db, 0, "shop_firm_rename", character.id, old_value={"name": old}, new_value={"name": name},
    )
    return old
