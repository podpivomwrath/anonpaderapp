"""Магазин мини-аппа (2026-10-13): товары за самоцветы.

Пока товар один - Метка Хранителя на 1-30 дней (premium_config.shop_price).
Каталог отдаётся целиком с ценами на каждый срок: ползунок на фронтенде
показывает цену сразу, а сервер при покупке считает её заново - цене с
клиента не верим.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import dailies_config as dc
from game.economy import gem_goods_config as ggc
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
        }, elixir_pack_item(), tincture_item(character), pocket_item(character), faction_item(character),
            courier_item(character), *house_items(character),
            *rename_items(character, firm_name)],
    }


# --- Набор зелий (2026-10-19, решение владельца) ---

ELIXIR_PACK_ID = "elixir_pack"
ELIXIR_PACK_PRICE = 100
ELIXIR_PACK_HEAL = ("heal_large", 10)
ELIXIR_PACK_COMBAT_EACH = 2


def _elixir_pack_contents() -> list[tuple[object, int]]:
    from services import elixir_service

    heal_id, heal_n = ELIXIR_PACK_HEAL
    rows = [(elixir_service.elixir_def(heal_id), heal_n)]
    rows += [(d, ELIXIR_PACK_COMBAT_EACH) for d in elixir_service.elixir_defs_ordered() if d.category == "combat"]
    return [(d, n) for d, n in rows if d is not None]


def elixir_pack_item() -> dict:
    return {
        "id": ELIXIR_PACK_ID, "title": "Набор зелий", "emoji": "🧪", "kind": "bundle",
        "price": ELIXIR_PACK_PRICE,
        "perks": [f"{d.emoji} {d.name} ×{n}" for d, n in _elixir_pack_contents()],
        "note": "Зелья сразу попадают в сумку.",
    }


async def buy_elixir_pack(db: AsyncSession, character: Character) -> list[str]:
    """Списать самоцветы и выдать набор. Возвращает строки содержимого."""
    from services import elixir_service

    try:
        await wallet_service.charge(db, character.id, "donate", ELIXIR_PACK_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise ShopError(f"Не хватает самоцветов: нужно 💎{ELIXIR_PACK_PRICE}.") from None
    contents = _elixir_pack_contents()
    for d, n in contents:
        await elixir_service.grant(db, character.id, d.id, n)
    return [f"{d.emoji} {d.name} ×{n}" for d, n in contents]


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


# --- Настойка пепла, секретный карман, смена фракции (2026-10-19) ---
# Числа - game/economy/gem_goods_config.py.

TINCTURE_ID = ggc.TINCTURE_ID
POCKET_ID = ggc.POCKET_ID
FACTION_ID = ggc.FACTION_ID


def tincture_item(character: Character) -> dict:
    from services import death_service

    active = death_service.tincture_active(character)
    return {
        "id": TINCTURE_ID, "title": "Настойка пепла", "emoji": "🫗", "kind": "bundle",
        "price": ggc.TINCTURE_PRICE,
        "perks": [
            f"{ggc.TINCTURE_HOURS} часа после покупки смерть не отнимает опыт",
            "Действует и в PvP, если на тебе клеймо",
            f"Ещё одна покупка добавляет {ggc.TINCTURE_HOURS} часа к оставшемуся времени",
        ],
        "note": "Пьётся сразу при покупке. Таймер идёт и когда ты не в игре.",
        "active_until": character.ash_tincture_until.isoformat() if active else None,
    }


async def buy_tincture(db: AsyncSession, character: Character, now: datetime | None = None) -> datetime:
    """Выпить настойку: срок от сейчас или сверху оставшегося."""
    from services import death_service

    now = now or datetime.now(timezone.utc)
    await _charge(db, character, ggc.TINCTURE_PRICE)
    start = character.ash_tincture_until if death_service.tincture_active(character, now) else now
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    character.ash_tincture_until = start + timedelta(hours=ggc.TINCTURE_HOURS)
    await db.flush()
    return character.ash_tincture_until


def pocket_item(character: Character) -> dict:
    return {
        "id": POCKET_ID, "title": "Секретный карман", "emoji": "🎒", "kind": "bundle",
        "price": ggc.POCKET_PRICE,
        "perks": [
            "При смерти половина реликвий остаётся у тебя",
            "Работает и в PvP: победитель забирает только вторую половину",
            "Покупается один раз и навсегда",
        ],
        "note": "Из нечётного стака в кармане остаётся на одну больше, так что одиночная реликвия не сгорает.",
        "available": not character.secret_pocket,
        "unavailable": "Карман уже пришит.",
    }


async def buy_pocket(db: AsyncSession, character: Character) -> None:
    if character.secret_pocket:
        raise ShopError("Карман уже пришит.")
    await _charge(db, character, ggc.POCKET_PRICE)
    character.secret_pocket = True
    await db.flush()


def faction_available_at(character: Character) -> datetime | None:
    """Когда можно сменить фракцию снова (None - уже можно)."""
    last = character.faction_changed_at
    if last is None:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    ready = last + timedelta(days=ggc.FACTION_COOLDOWN_DAYS)
    return ready if ready > datetime.now(timezone.utc) else None


def faction_item(character: Character) -> dict:
    from bot.onboarding_texts import REGION_TITLES
    from game.economy import faction_config as fc

    ready = faction_available_at(character)
    return {
        "id": FACTION_ID, "title": "Смена фракции", "emoji": "🏳", "kind": "faction",
        "price": ggc.FACTION_PRICE,
        "current": REGION_TITLES.get(character.region or "", ""),
        "options": [{"id": c, "title": REGION_TITLES[c]} for c in fc.CITIES if c != character.region],
        "perks": [
            "Сразу переносит на площадь нового города",
            "Долгий путь прерывается: награда за прошедшие часы остаётся, снаряжение переезжает с тобой",
            "Поездка, исследование и рыбалка отменяются",
            "Сюжет нового города открывается на том же акте",
            "Новые обозы фирмы выходят из нового города, товар в пути и на складе остаётся",
        ],
        "note": f"Менять фракцию можно раз в {ggc.FACTION_COOLDOWN_DAYS} дней. Купишь в бою - переезд случится, "
                "когда бой закончится.",
        "available": ready is None and character.pending_faction is None,
        "available_at": ready.isoformat() if ready is not None else None,
        "pending": REGION_TITLES.get(character.pending_faction) if character.pending_faction else None,
    }


async def change_faction(
    db: AsyncSession, character: Character, region, now: datetime | None = None, defer: bool = False,
) -> str | None:
    """Переезд в другой город. Возвращает итог прерванного похода (или None).
    Бои, рейды, разломы и висящие события проверяет вызывающий: они живут
    в памяти бота, а не в базе. Занят или мёртв (defer) - самоцветы
    списываются сейчас, а переезд ждёт в pending_faction, пока бой не
    кончится (решение владельца 2026-10-19): его делает move_pending."""
    from game.economy import faction_config as fc
    from services import death_service

    now = now or datetime.now(timezone.utc)
    if region not in fc.CITIES:
        raise ShopError("Выбери город.")
    if character.pending_faction is not None:
        raise ShopError("Переезд уже оплачен - он случится после боя.")
    if region == character.region:
        raise ShopError("Ты и так живёшь в этом городе.")
    if faction_available_at(character) is not None:
        raise ShopError(f"Фракцию меняют не чаще раза в {ggc.FACTION_COOLDOWN_DAYS} дней.")
    await _charge(db, character, ggc.FACTION_PRICE)
    character.faction_changed_at = now
    if defer or death_service.is_dead(character, now):
        character.pending_faction = region
        await db.flush()
        await _log_faction(db, character, region, pending=True)
        return None
    return await _move(db, character, region, now)


async def move_pending(db: AsyncSession, character: Character, now: datetime | None = None) -> str | None:
    """Оплаченный в бою переезд - когда бой кончился и персонаж жив."""
    region = character.pending_faction
    character.pending_faction = None
    if region is None or region == character.region:
        await db.flush()
        return None
    return await _move(db, character, region, now or datetime.now(timezone.utc))


async def _log_faction(db: AsyncSession, character: Character, region: str, pending: bool = False) -> None:
    from services import admin_service

    await admin_service.log_action(
        db, 0, "shop_faction", character.id, old_value={"region": character.region},
        new_value={"region": region, "pending": pending},
    )


async def _move(db: AsyncSession, character: Character, region: str, now: datetime) -> str | None:
    from game.world import world_config as wc
    from services import (
        admin_service, fishing_service, mining_service, mount_service,
        movement_service, pk_service, screen_service, story_service, voyage_service,
    )

    old = character.region

    voyage_text = None
    voyage = await voyage_service.get(db, character.id, lock=True)
    if voyage is not None:
        if voyage.status == "away":
            voyage_text = voyage_service._finish(voyage, early=True)
        voyage.region = region

    await story_service.carry_over(db, character, old, region)
    character.region = region

    if movement_service.is_traveling(character, now):
        movement_service.cancel_travel(character)
    travel = await mount_service.active_travel(db, character.id)
    if travel is not None:
        await mount_service.cancel_travel(db, travel)
    fishing_service.clear_cast(character)
    await mining_service.cancel_dig(db, character)
    character.pos_x, character.pos_y = wc.CITY_COORDS[region]
    if pk_service.city_banned(character):
        from bot.handlers.respawn import _outside_gate

        character.pos_x, character.pos_y = _outside_gate(region)
    await screen_service.set_screen(db, character, None)
    await db.flush()
    await admin_service.log_action(
        db, 0, "shop_faction_move", character.id, old_value={"region": old}, new_value={"region": region},
    )
    return voyage_text


# --- Курьер (2026-10-19): питомец-доставщик, services/courier_service.py ---

COURIER_ID = "courier"


def courier_item(character: Character) -> dict:
    from game.economy import courier_config as cc

    return {
        "id": COURIER_ID, "title": "Курьер", "emoji": cc.EMOJI, "kind": "bundle", "price": cc.PRICE,
        "perks": [
            "Носит вещи, зелья и руду тому, кто далеко от тебя",
            "Выходит из твоего города, забирает посылку у тебя и бежит к получателю",
            "Получатель сменил клетку - курьер поворачивает за ним прямо в дороге",
            "Получатель в бою или рейде - курьер ждёт рядом и отдаёт посылку после боя",
            "Покупается один раз и навсегда",
        ],
        "note": "Рядом с тобой и золото с самоцветами передаются и без курьера, как раньше. "
                "Одна посылка за раз: следующую он возьмёт, когда отдаст эту.",
        "available": not character.has_courier,
        "unavailable": "Курьер у тебя уже есть.",
    }


# --- Дом (2026-10-21): печь и алхимический стол, game/economy/house_config.py ---

HOUSE_ID = "house"


def house_items(character: Character) -> list[dict]:
    from game.economy import house_config as hc

    if not hc.ON_SALE:
        return []
    return [{
        "id": HOUSE_ID, "title": "Дом", "emoji": hc.EMOJI, "kind": "bundle", "price": hc.PRICE,
        "perks": [
            "Свой дом в родном городе, кнопка «Дом» на площади",
            "Печь: готовишь блюда из рыбы и трав, они дают бафф на 30 минут",
            "Алхимический стол: сам варишь зелья из лавки, выходит дешевле",
            "Переезжаешь в другой город - дом переезжает с тобой",
            "Покупается один раз и навсегда",
        ],
        "note": "Травы собирать можно и без дома, а варить зелья и готовить еду - только дома.",
        "available": not character.has_house,
        "unavailable": "Дом у тебя уже есть.",
    }]


async def buy_house(db: AsyncSession, character: Character) -> None:
    from game.economy import house_config as hc

    if not hc.ON_SALE:
        raise ShopError("Дом пока не продаётся.")
    if character.has_house:
        raise ShopError("Дом у тебя уже есть.")
    try:
        await wallet_service.charge(db, character.id, "donate", hc.PRICE)
    except wallet_service.NotEnoughCurrency:
        raise ShopError(f"Не хватает самоцветов: нужно 💎{hc.PRICE}.") from None
    character.has_house = True
    await db.flush()


async def buy_courier(db: AsyncSession, character: Character) -> None:
    from services import courier_service

    try:
        await courier_service.buy(db, character)
    except courier_service.CourierError as exc:
        raise ShopError(str(exc)) from None
