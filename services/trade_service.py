"""Ремесло «Торговля»: повозка, Торговый дом, караваны, потери груза.

Числа - game/economy/trade_config.py. Повозка ездит тем же движением по
клеткам, что и маунт (services/mount_service.py, mount_id = CART_MOUNT_ID):
шаг - от лошадей, шанс нападения - от охраны.

Все деньги - через атомарный кошелёк (wallet_service), груз и давление
рынка - под блокировкой строк: два одновременных нажатия не продадут один
ящик дважды и не купят по одной цене.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import trade_config as tc
from game.world import grid
from game.world import world_config as wc
from models import Character, CharacterCart, CharacterOre, MountTravel, TradeCaravan, TradeMarket
from services import lootbox_service, mount_service, wallet_service


class TradeError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Повозка ---


async def get_cart(db: AsyncSession, character_id: int, lock: bool = False) -> CharacterCart | None:
    query = select(CharacterCart).where(CharacterCart.character_id == character_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


def part_value(cart: CharacterCart, part_id: str):
    part = tc.PARTS_BY_ID[part_id]
    return part.values[getattr(cart, part_id) - 1]


def capacity(cart: CharacterCart) -> int:
    return part_value(cart, "body")


def crates(cart: CharacterCart) -> int:
    return sum((cart.cargo or {}).values())


def max_durability(cart: CharacterCart) -> int:
    return part_value(cart, "plating")


def trip_ambush(cart: CharacterCart) -> float:
    return tc.CART_TRIP_AMBUSH * part_value(cart, "guard")


async def cart_travel(db: AsyncSession, character_id: int) -> MountTravel | None:
    travel = await mount_service.active_travel(db, character_id)
    return travel if travel is not None and travel.mount_id == tc.CART_MOUNT_ID else None


def _city_here(character: Character) -> str | None:
    return grid.city_region_at(character.pos_x, character.pos_y)


async def buy_cart(db: AsyncSession, character: Character) -> CharacterCart:
    if character.level < tc.TRADE_MIN_LEVEL:
        raise TradeError(f"Торговать можно с {tc.TRADE_MIN_LEVEL} уровня.")
    if _city_here(character) is None:
        raise TradeError("Повозку продают в Торговом доме города.")
    if await get_cart(db, character.id) is not None:
        raise TradeError("Повозка у тебя уже есть.")
    try:
        await wallet_service.charge(db, character.id, "farm", tc.CART_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Повозка стоит {tc.CART_PRICE} золота.") from None
    cart = CharacterCart(
        character_id=character.id, cart_x=character.pos_x, cart_y=character.pos_y,
        horses=1, body=1, plating=1, guard=1, durability=tc.PARTS_BY_ID["plating"].values[0],
        cargo={}, paid={}, trade_level=1, trade_xp=0, profit_total=0,
    )
    db.add(cart)
    await db.flush()
    return cart


async def _require_cart_here(db: AsyncSession, character: Character, lock: bool = True) -> CharacterCart:
    cart = await get_cart(db, character.id, lock=lock)
    if cart is None:
        raise TradeError("У тебя нет повозки. Её продают в Торговом доме любого города.")
    if await cart_travel(db, character.id) is not None:
        raise TradeError("Повозка в пути.")
    if (cart.cart_x, cart.cart_y) != (character.pos_x, character.pos_y):
        raise TradeError(f"Повозка осталась в ({cart.cart_x}; {cart.cart_y}). Торговать можно только рядом с ней.")
    return cart


# --- Цены ---


async def _market_row(db: AsyncSession, city: str, good_id: str, lock: bool, now: datetime) -> TradeMarket:
    query = select(TradeMarket).where(TradeMarket.city == city, TradeMarket.good_id == good_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        row = TradeMarket(city=city, good_id=good_id, pressure=0.0, updated_at=now)
        db.add(row)
        await db.flush()
    hours = max((now - _aware(row.updated_at)).total_seconds() / 3600, 0.0)
    if hours > 0 and row.pressure:
        row.pressure = max(row.pressure - tc.RECOVERY_PER_HOUR * hours, 0.0)
    row.updated_at = now
    return row


def _sell_mult(city: str, good: tc.Good) -> float:
    return tc.SELL_MULT_DEFICIT if good.city in tc.DEFICIT[city] else tc.SELL_MULT_NORMAL


def city_buy_price(city: str, good: tc.Good, pressure: float) -> int | None:
    """Цена ящика у производителя (игрок покупает). Только свои товары."""
    if good.city != city:
        return None
    return round(tc.TIER_BASE_PRICE[good.tier] * tc.BUY_MULT * (1 + min(pressure, tc.MAX_PRESSURE)))


def city_sell_price(city: str, good: tc.Good, pressure: float) -> int | None:
    """Сколько город платит за ящик (игрок продаёт). Своё не покупает."""
    if good.city == city:
        return None
    return round(tc.TIER_BASE_PRICE[good.tier] * _sell_mult(city, good) * (1 - min(pressure, tc.MAX_PRESSURE)))


def caravan_buy_price(good: tc.Good) -> int:
    """Караван продаёт игроку."""
    return round(tc.TIER_BASE_PRICE[good.tier] * tc.CARAVAN_SELL_MULT)


def caravan_sell_price(good: tc.Good) -> int:
    """Караван покупает у игрока."""
    return round(tc.TIER_BASE_PRICE[good.tier] * tc.CARAVAN_BUY_MULT)


# --- Место торговли ---


@dataclass
class Place:
    kind: str                      # "city" | "caravan"
    title: str
    city: str | None = None
    caravan: TradeCaravan | None = None


async def caravan_at(db: AsyncSession, x: int, y: int, now: datetime | None = None, lock: bool = False) -> TradeCaravan | None:
    now = now or _now()
    query = select(TradeCaravan).where(TradeCaravan.x == x, TradeCaravan.y == y, TradeCaravan.expires_at > now)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def place_here(db: AsyncSession, character: Character, lock: bool = False) -> Place | None:
    city = _city_here(character)
    if city is not None:
        from bot.onboarding_texts import REGION_TITLES  # избегаем цикла импортов

        return Place("city", f"Торговый дом · {REGION_TITLES[city]}", city=city)
    caravan = await caravan_at(db, character.pos_x, character.pos_y, lock=lock)
    if caravan is not None:
        return Place("caravan", f"Караван на ({caravan.x}; {caravan.y})", caravan=caravan)
    return None


@dataclass
class Offer:
    good: tc.Good
    buy: int | None        # игрок может купить по этой цене
    sell: int | None       # игрок может продать по этой цене
    stock: int | None = None   # остаток у каравана


async def offers(db: AsyncSession, place: Place, now: datetime | None = None) -> list[Offer]:
    now = now or _now()
    out = []
    if place.kind == "city":
        for good in tc.GOODS:
            row = await _market_row(db, place.city, good.id, lock=False, now=now)
            out.append(Offer(good, city_buy_price(place.city, good, row.pressure), city_sell_price(place.city, good, row.pressure)))
        return out
    caravan = place.caravan
    for good_id, left in (caravan.sells or {}).items():
        good = tc.GOODS_BY_ID[good_id]
        out.append(Offer(good, caravan_buy_price(good), None, left))
    for good_id, left in (caravan.buys or {}).items():
        good = tc.GOODS_BY_ID[good_id]
        out.append(Offer(good, None, caravan_sell_price(good), left))
    return out


# --- Сделки ---


def _check_count(count) -> int:
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 50:
        raise TradeError("Ящиков - от 1 до 50 за раз.")
    return count


def _good(good_id) -> tc.Good:
    good = tc.GOODS_BY_ID.get(good_id) if isinstance(good_id, str) else None
    if good is None:
        raise TradeError("Такого товара нет.")
    return good


@dataclass
class Deal:
    good: tc.Good
    count: int
    gold: int
    profit: int = 0
    xp: int = 0
    level_up: int | None = None
    chests: int = 0
    lines: list[str] = field(default_factory=list)


async def buy(db: AsyncSession, character: Character, good_id, count) -> Deal:
    good, count = _good(good_id), _check_count(count)
    cart = await _require_cart_here(db, character)
    if cart.trade_level < tc.TIER_MIN_TRADE_LEVEL[good.tier]:
        raise TradeError(
            f"{tc.TIER_NAMES[good.tier].capitalize()} товар - с {tc.TIER_MIN_TRADE_LEVEL[good.tier]} уровня торговли."
        )
    if crates(cart) + count > capacity(cart):
        raise TradeError(f"В кузов влезет ещё {capacity(cart) - crates(cart)} ящ. (всего {capacity(cart)}).")
    place = await place_here(db, character, lock=True)
    now = _now()
    if place is None:
        raise TradeError("Покупать можно в Торговом доме города или у каравана.")
    if place.kind == "city":
        if good.city != place.city:
            raise TradeError("Этот товар здесь не производят - его продают в своём городе.")
        row = await _market_row(db, place.city, good.id, lock=True, now=now)
        total = 0
        for _ in range(count):
            total += city_buy_price(place.city, good, row.pressure)
            row.pressure += tc.SATURATION_PER_CRATE
    else:
        left = (place.caravan.sells or {}).get(good.id)
        if left is None:
            raise TradeError("Караван этот товар не продаёт.")
        if left < count:
            raise TradeError(f"У каравана осталось {left} ящ.")
        total = caravan_buy_price(good) * count
        place.caravan.sells = {**place.caravan.sells, good.id: left - count}
    try:
        await wallet_service.charge(db, character.id, "farm", total)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Не хватает золота: {count} ящ. стоят {total}.") from None
    cart.cargo = {**(cart.cargo or {}), good.id: (cart.cargo or {}).get(good.id, 0) + count}
    cart.paid = {**(cart.paid or {}), good.id: (cart.paid or {}).get(good.id, 0) + total}
    await db.flush()
    return Deal(good, count, total)


async def sell(db: AsyncSession, character: Character, good_id, count, rng: random.Random | None = None) -> Deal:
    good, count = _good(good_id), _check_count(count)
    rng = rng or random.Random()
    cart = await _require_cart_here(db, character)
    have = (cart.cargo or {}).get(good.id, 0)
    if have < count:
        raise TradeError(f"В повозке {have} ящ. этого товара.")
    place = await place_here(db, character, lock=True)
    now = _now()
    if place is None:
        raise TradeError("Продавать можно в Торговом доме города или каравану.")
    if place.kind == "city":
        if good.city == place.city:
            raise TradeError("Свой товар город не покупает - вези туда, где его нет.")
        row = await _market_row(db, place.city, good.id, lock=True, now=now)
        total = 0
        for _ in range(count):
            total += city_sell_price(place.city, good, row.pressure)
            row.pressure += tc.SATURATION_PER_CRATE
    else:
        left = (place.caravan.buys or {}).get(good.id)
        if left is None:
            raise TradeError("Караван этот товар не покупает.")
        if left < count:
            raise TradeError(f"Каравану нужно ещё только {left} ящ.")
        total = caravan_sell_price(good) * count
        place.caravan.buys = {**place.caravan.buys, good.id: left - count}
    # Себестоимость проданных ящиков - средняя по уплаченному за этот товар.
    paid_all = (cart.paid or {}).get(good.id, 0)
    cost = round(paid_all * count / have) if have else 0
    cargo = dict(cart.cargo)
    paid = dict(cart.paid or {})
    if have == count:
        cargo.pop(good.id, None)
        paid.pop(good.id, None)
    else:
        cargo[good.id] = have - count
        paid[good.id] = paid_all - cost
    cart.cargo, cart.paid = cargo, paid
    await wallet_service.deposit(db, character.id, "farm", total)
    deal = Deal(good, count, total, profit=total - cost)
    cart.profit_total += max(deal.profit, 0)
    deal.xp = tc.XP_PER_CRATE[good.tier] * count
    cart.trade_xp += deal.xp
    while cart.trade_xp >= tc.xp_to_next(cart.trade_level):
        cart.trade_xp -= tc.xp_to_next(cart.trade_level)
        cart.trade_level += 1
        deal.level_up = cart.trade_level
    chance = tc.CHEST_CHANCE_PER_CRATE[good.tier]
    for _ in range(count):
        if rng.random() < chance:
            await lootbox_service.grant_chest(db, character, 0)
            deal.chests += 1
    await db.flush()
    return deal


# --- Улучшения и ремонт ---


def upgrade_cost(cart: CharacterCart, part_id: str) -> tuple[int, str, int] | None:
    level = getattr(cart, part_id)
    if level >= len(tc.PARTS_BY_ID[part_id].values):
        return None
    return tc.UPGRADE_COST[level - 1]


async def upgrade(db: AsyncSession, character: Character, part_id) -> CharacterCart:
    if part_id not in tc.PARTS_BY_ID:
        raise TradeError("Нет такой части повозки.")
    if _city_here(character) is None:
        raise TradeError("Улучшать повозку можно в городе.")
    cart = await _require_cart_here(db, character)
    cost = upgrade_cost(cart, part_id)
    if cost is None:
        raise TradeError("Эта часть уже улучшена до предела.")
    gold, ore_id, ore_count = cost
    from game.economy import mining

    ore = mining.ore_def(ore_id)
    result = await db.execute(
        update(CharacterOre).where(
            CharacterOre.character_id == character.id, CharacterOre.ore_id == ore_id,
            CharacterOre.grade == "common", CharacterOre.count >= ore_count,
        ).values(count=CharacterOre.count - ore_count)
    )
    if not result.rowcount:
        raise TradeError(f"Нужно {ore_count} шт. обычной руды «{ore.name if ore else ore_id}».")
    try:
        await wallet_service.charge(db, character.id, "farm", gold)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Нужно {gold} золота.") from None
    setattr(cart, part_id, getattr(cart, part_id) + 1)
    if part_id == "plating":
        # Новая обшивка ставится целой.
        cart.durability = max_durability(cart)
    await db.flush()
    return cart


def repair_cost(cart: CharacterCart) -> int:
    return (max_durability(cart) - cart.durability) * tc.REPAIR_PER_POINT


async def repair(db: AsyncSession, character: Character) -> int:
    if _city_here(character) is None:
        raise TradeError("Чинить повозку можно в городе.")
    cart = await _require_cart_here(db, character)
    cost = repair_cost(cart)
    if cost <= 0:
        raise TradeError("Обшивка цела.")
    try:
        await wallet_service.charge(db, character.id, "farm", cost)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Ремонт стоит {cost} золота.") from None
    cart.durability = max_durability(cart)
    await db.flush()
    return cost


# --- Поездка ---


async def send(db: AsyncSession, character: Character, to_x, to_y) -> MountTravel:
    if not isinstance(to_x, int) or not isinstance(to_y, int) or isinstance(to_x, bool) or isinstance(to_y, bool):
        raise TradeError("Неверная точка.")
    if not grid.in_bounds(to_x, to_y):
        raise TradeError(f"Мир кончается в {wc.WORLD_RADIUS} клетках от Монолита.")
    cart = await _require_cart_here(db, character)
    if (to_x, to_y) == (character.pos_x, character.pos_y):
        raise TradeError("Повозка уже здесь.")
    if await mount_service.active_travel(db, character.id) is not None:
        raise TradeError("Ты уже в пути.")
    return await mount_service.start_travel(
        db, character, tc.CART_MOUNT_ID, to_x, to_y, step_seconds=part_value(cart, "horses"),
    )


def _lose(cart: CharacterCart, share: float, rng: random.Random) -> dict[str, int]:
    """Теряет долю ящиков (с округлением вверх), случайно по товарам."""
    cargo = dict(cart.cargo or {})
    total = sum(cargo.values())
    n = min(math.ceil(total * share), total)
    lost: dict[str, int] = {}
    paid = dict(cart.paid or {})
    for _ in range(n):
        good_id = rng.choice([g for g, c in cargo.items() if c > 0])
        per = paid.get(good_id, 0) / cargo[good_id] if cargo[good_id] else 0
        cargo[good_id] -= 1
        paid[good_id] = round(paid.get(good_id, 0) - per)
        lost[good_id] = lost.get(good_id, 0) + 1
        if cargo[good_id] == 0:
            cargo.pop(good_id)
            paid.pop(good_id, None)
    cart.cargo, cart.paid = cargo, paid
    return lost


def lost_text(lost: dict[str, int]) -> str:
    return ", ".join(f"{tc.GOODS_BY_ID[g].emoji} {tc.GOODS_BY_ID[g].name} ×{n}" for g, n in lost.items())


async def on_arrival(db: AsyncSession, character: Character) -> CharacterCart | None:
    cart = await get_cart(db, character.id, lock=True)
    if cart is not None:
        cart.cart_x, cart.cart_y = character.pos_x, character.pos_y
    return cart


async def on_ambush_won(db: AsyncSession, character: Character, rng: random.Random | None = None) -> str | None:
    """Отбился в пути: обшивка теряет единицу прочности, выбита - часть
    груза рассыпается. Возвращает строку для игрока."""
    rng = rng or random.Random()
    cart = await get_cart(db, character.id, lock=True)
    if cart is None:
        return None
    cart.durability = max(cart.durability - 1, 0)
    if cart.durability > 0:
        return f"🛡 Обшивка повозки держится: ещё {cart.durability} нападений."
    lost = _lose(cart, tc.LOSS_ON_BREAK, rng)
    await db.flush()
    if not lost:
        return "🛡 Обшивка выбита - почини её в городе."
    return f"💥 Обшивка выбита, часть груза рассыпалась: {lost_text(lost)}. Почини повозку в городе."


async def on_death(db: AsyncSession, character: Character, rng: random.Random | None = None) -> str | None:
    """Погиб в пути с повозкой: часть груза пропала, повозку с остатком
    находят и пригоняют в родной город."""
    rng = rng or random.Random()
    cart = await get_cart(db, character.id, lock=True)
    if cart is None:
        return None
    lost = _lose(cart, tc.LOSS_ON_DEATH, rng)
    home = wc.CITY_COORDS.get(character.region) or (cart.cart_x, cart.cart_y)
    cart.cart_x, cart.cart_y = home
    await db.flush()
    lost_line = f" Пропало: {lost_text(lost)}." if lost else ""
    return f"🐂 Повозку с остатком груза пригнали в родной город.{lost_line}"


async def rob(db: AsyncSession, winner: Character, loser: Character, rng: random.Random | None = None) -> tuple[dict, int]:
    """Победа в PvP над торговцем в пути (кольца 3-5): победитель забирает
    долю груза и сбывает её за долю базовой цены. ({товар: ящ}, золото)."""
    rng = rng or random.Random()
    if grid.ring_tier(loser.pos_x, loser.pos_y) < tc.ROB_MIN_RING:
        return {}, 0
    if await cart_travel(db, loser.id) is None:
        return {}, 0
    cart = await get_cart(db, loser.id, lock=True)
    if cart is None or not cart.cargo:
        return {}, 0
    lost = _lose(cart, tc.ROB_SHARE, rng)
    gold = round(sum(tc.TIER_BASE_PRICE[tc.GOODS_BY_ID[g].tier] * n for g, n in lost.items()) * tc.ROB_GOLD_SHARE)
    if gold:
        await wallet_service.deposit(db, winner.id, "farm", gold)
    await db.flush()
    return lost, gold


async def after_pvp_death(db: AsyncSession, loser: Character) -> None:
    """Торговец пал в PvP в пути: поездка кончена, повозку с остатком
    пригоняют в родной город (груз уже поделён в rob, второй раз не теряется)."""
    travel = await cart_travel(db, loser.id)
    if travel is None:
        return
    await mount_service.cancel_travel(db, travel)
    cart = await get_cart(db, loser.id, lock=True)
    if cart is not None:
        cart.cart_x, cart.cart_y = wc.CITY_COORDS.get(loser.region) or (cart.cart_x, cart.cart_y)
    await db.flush()


# --- Караваны ---


async def active_caravans(db: AsyncSession, now: datetime | None = None) -> list[TradeCaravan]:
    now = now or _now()
    return list((await db.scalars(select(TradeCaravan).where(TradeCaravan.expires_at > now).order_by(TradeCaravan.id))).all())


async def caravan_tick(db: AsyncSession, rng: random.Random | None = None, now: datetime | None = None) -> TradeCaravan | None:
    """Раз в CARAVAN_CHECK_MINUTES: если караванов меньше максимума - с
    шансом появляется новый на случайной клетке колец 2-3."""
    rng = rng or random.Random()
    now = now or _now()
    if len(await active_caravans(db, now)) >= tc.CARAVAN_MAX or rng.random() >= tc.CARAVAN_SPAWN_CHANCE:
        return None
    return await spawn_caravan(db, rng, now)


async def spawn_caravan(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> TradeCaravan:
    now = now or _now()
    cells = [
        (x, y) for x, y in grid.all_cells()
        if grid.ring_tier(x, y) in tc.CARAVAN_RINGS and not mount_service._is_safe_cell(x, y)
    ]
    x, y = rng.choice(cells)
    goods = list(tc.GOODS)
    rng.shuffle(goods)
    buys = {g.id: tc.CARAVAN_STOCK for g in goods[:rng.randint(1, 2)]}
    rest = [g for g in goods if g.id not in buys]
    sells = {g.id: tc.CARAVAN_STOCK for g in rest[:rng.randint(1, 2)]}
    caravan = TradeCaravan(
        x=x, y=y, buys=buys, sells=sells, created_at=now,
        expires_at=now + timedelta(minutes=tc.CARAVAN_LIFETIME_MINUTES),
    )
    db.add(caravan)
    await db.flush()
    return caravan
