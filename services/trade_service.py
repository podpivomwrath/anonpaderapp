"""Ремесло «Торговля»: торговая фирма и её повозки (2026-10-15).

Игрок управляет фирмой удалённо: закупает товар города, где стоит
повозка, выбирает город назначения и путь и отправляет повозку. Она едет
сама (персонаж свободен), по прибытии продаёт весь груз по цене на месте и
встаёт в этом городе. Нападения в пути разыгрываются при отправке и
применяются по прибытии (обшивка, потеря части груза) - без боя.

Числа - game/economy/trade_config.py. Деньги - через атомарный кошелёк
(wallet_service), груз и давление рынка - под блокировкой строк.
"""

import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import faction_config as fc
from game.economy import trade_config as tc
from game.world import grid
from game.world import world_config as wc
from models import Character, CharacterOre, TradeCart, TradeFirm, TradeMarket, TradeOrder, TradeTrip
from services import faction_service, lootbox_service, wallet_service


class TradeError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def city_title(city: str) -> str:
    from bot.onboarding_texts import REGION_TITLES  # избегаем цикла импортов

    return REGION_TITLES[city]


# --- Фирма ---

_NAME_RE = re.compile(r"^[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё \-]*$")


def clean_name(name) -> str:
    return re.sub(r"\s+", " ", name).strip() if isinstance(name, str) else ""


async def get_firm(db: AsyncSession, character_id: int, lock: bool = False) -> TradeFirm | None:
    query = select(TradeFirm).where(TradeFirm.character_id == character_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(query)


async def _check_name(db: AsyncSession, name: str) -> str:
    from services import onboarding_service

    name = clean_name(name)
    if not tc.FIRM_NAME_MIN <= len(name) <= tc.FIRM_NAME_MAX:
        raise TradeError(f"Название - от {tc.FIRM_NAME_MIN} до {tc.FIRM_NAME_MAX} символов.")
    if not _NAME_RE.match(name):
        raise TradeError("В названии - только буквы, цифры, пробел и дефис.")
    if onboarding_service.contains_banned_word(name):
        raise TradeError("Такое название не пройдёт - выбери другое.")
    if await db.scalar(select(TradeFirm.character_id).where(TradeFirm.name_key == name.lower())) is not None:
        raise TradeError("Фирма с таким названием уже есть.")
    return name


def _home(character: Character) -> str:
    if character.region not in fc.CITIES:
        raise TradeError("Сначала закончи создание персонажа.")
    return character.region


async def buy_firm(db: AsyncSession, character: Character, name=None) -> TradeFirm:
    """Покупка фирмы. Название (решение владельца 2026-10-15) - сразу после
    покупки отдельным шагом (name_firm); здесь - только если передано."""
    if character.level < tc.TRADE_MIN_LEVEL:
        raise TradeError(f"Торговать можно с {tc.TRADE_MIN_LEVEL} уровня.")
    home = _home(character)
    if await get_firm(db, character.id) is not None:
        raise TradeError("Фирма у тебя уже есть.")
    name = await _check_name(db, name) if name is not None else None
    try:
        await wallet_service.charge(db, character.id, "farm", tc.FIRM_PRICE)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Фирма стоит {tc.FIRM_PRICE} золота.") from None
    firm = TradeFirm(
        character_id=character.id, name=name, name_key=name.lower() if name else None, trade_level=1, trade_xp=0,
        profit_total=0, notify_arrival=True, notify_orders=False,
    )
    db.add(firm)
    db.add(_new_cart(character.id, 1, home))
    await db.flush()
    return firm


async def name_firm(db: AsyncSession, character: Character, name) -> TradeFirm:
    """Название фирмы - сразу после покупки или переноса со старой повозки.
    Менять пока нельзя."""
    firm = await get_firm(db, character.id, lock=True)
    if firm is None:
        raise TradeError("Фирмы нет.")
    if firm.name:
        raise TradeError("Название уже есть - менять его пока нельзя.")
    name = await _check_name(db, name)
    firm.name, firm.name_key = name, name.lower()
    await db.flush()
    return firm


async def require_firm(db: AsyncSession, character: Character, lock: bool = False) -> TradeFirm:
    firm = await get_firm(db, character.id, lock=lock)
    if firm is None:
        raise TradeError("Сначала открой торговую фирму.")
    if not firm.name:
        raise TradeError("Сначала дай фирме название.")
    return firm


async def set_notify(db: AsyncSession, character: Character, arrival=None, orders=None) -> TradeFirm:
    firm = await require_firm(db, character, lock=True)
    if isinstance(arrival, bool):
        firm.notify_arrival = arrival
    if isinstance(orders, bool):
        firm.notify_orders = orders
    await db.flush()
    return firm


# --- Повозки ---


def _new_cart(character_id: int, slot: int, city: str) -> TradeCart:
    return TradeCart(
        character_id=character_id, slot=slot, city=city, status="idle", ambushes=0,
        horses=1, body=1, plating=1, guard=1, durability=tc.PARTS_BY_ID["plating"].values[0],
        cargo={}, paid={},
    )


async def carts(db: AsyncSession, character_id: int) -> list[TradeCart]:
    return list((await db.scalars(
        select(TradeCart).where(TradeCart.character_id == character_id).order_by(TradeCart.slot)
    )).all())


async def get_cart(db: AsyncSession, character_id: int, slot, lock: bool = True) -> TradeCart:
    if not isinstance(slot, int) or isinstance(slot, bool):
        raise TradeError("Нет такой повозки.")
    query = select(TradeCart).where(TradeCart.character_id == character_id, TradeCart.slot == slot)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    cart = await db.scalar(query)
    if cart is None:
        raise TradeError("Нет такой повозки.")
    return cart


def part_value(cart: TradeCart, part_id: str):
    part = tc.PARTS_BY_ID[part_id]
    return part.values[min(getattr(cart, part_id), len(part.values)) - 1]


def capacity(cart: TradeCart) -> int:
    return part_value(cart, "body")


def crates(cart: TradeCart) -> int:
    return sum((cart.cargo or {}).values())


def max_durability(cart: TradeCart) -> int:
    return part_value(cart, "plating")


def next_slot_need(count: int) -> tuple[int, int] | None:
    """(уровень торговли, золото) для следующей повозки; None - предел."""
    return tc.CART_SLOTS.get(count + 1) if count < tc.MAX_CARTS else None


async def buy_cart(db: AsyncSession, character: Character) -> TradeCart:
    firm = await require_firm(db, character, lock=True)
    have = await db.scalar(select(func.count()).select_from(TradeCart).where(TradeCart.character_id == character.id))
    need = next_slot_need(have)
    if need is None:
        raise TradeError(f"У фирмы уже {tc.MAX_CARTS} повозки - больше не нужно.")
    level, gold = need
    if firm.trade_level < level:
        raise TradeError(f"Повозка №{have + 1} - с {level} уровня торговли.")
    try:
        await wallet_service.charge(db, character.id, "farm", gold)
    except wallet_service.NotEnoughCurrency:
        raise TradeError(f"Повозка №{have + 1} стоит {gold} золота.") from None
    cart = _new_cart(character.id, have + 1, _home(character))
    db.add(cart)
    await db.flush()
    return cart


def _require_idle(cart: TradeCart) -> None:
    if cart.status != "idle":
        raise TradeError("Повозка в пути.")


def upgrade_cost(cart: TradeCart, part_id: str) -> tuple[int, str, int] | None:
    level = getattr(cart, part_id)
    if level >= len(tc.PARTS_BY_ID[part_id].values):
        return None
    return tc.UPGRADE_COST[level - 1]


async def upgrade(db: AsyncSession, character: Character, slot, part_id) -> TradeCart:
    if part_id not in tc.PARTS_BY_ID:
        raise TradeError("Нет такой части повозки.")
    await require_firm(db, character)
    cart = await get_cart(db, character.id, slot)
    _require_idle(cart)
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
        cart.durability = max_durability(cart)  # новая обшивка ставится целой
    await db.flush()
    return cart


def repair_cost(cart: TradeCart) -> int:
    return max(max_durability(cart) - cart.durability, 0) * tc.REPAIR_PER_POINT


async def repair(db: AsyncSession, character: Character, slot) -> int:
    await require_firm(db, character)
    cart = await get_cart(db, character.id, slot)
    _require_idle(cart)
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


# --- Цены ---


async def market_row(db: AsyncSession, city: str, good_id: str, lock: bool, now: datetime) -> TradeMarket:
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


def sell_mult(city: str, good: tc.Good) -> float:
    return tc.SELL_MULT_DEFICIT if good.city in tc.DEFICIT[city] else tc.SELL_MULT_FAR


def city_buy_price(city: str, good: tc.Good, pressure: float) -> int | None:
    """Цена ящика у производителя (фирма покупает). Только свои товары."""
    if good.city != city:
        return None
    return round(tc.TIER_BASE_PRICE[good.tier] * tc.BUY_MULT * (1 + min(pressure, tc.MAX_PRESSURE)))


def city_sell_price(city: str, good: tc.Good, pressure: float) -> int | None:
    """Сколько город платит за ящик (до бонуса уровня торговли). Своё не покупает."""
    if good.city == city:
        return None
    return round(tc.TIER_BASE_PRICE[good.tier] * sell_mult(city, good) * (1 - min(pressure, tc.MAX_PRESSURE)))


async def pressures(db: AsyncSession, now: datetime | None = None) -> dict[tuple[str, str], float]:
    """Давление по всем (город, товар) сейчас - для показа цен."""
    now = now or _now()
    out = {}
    for row in (await db.scalars(select(TradeMarket))).all():
        hours = max((now - _aware(row.updated_at)).total_seconds() / 3600, 0.0)
        out[(row.city, row.good_id)] = max(row.pressure - tc.RECOVERY_PER_HOUR * hours, 0.0)
    return out


# --- Путь ---


def path(from_city: str, to_city: str, route: str) -> list[tuple[int, int]]:
    a, b = wc.CITY_COORDS[from_city], wc.CITY_COORDS[to_city]
    return grid.safe_path(*a, *b) if route == "safe" else grid.line_path(*a, *b)


def trip_seconds(cart: TradeCart, cells: int, route: str) -> float:
    mult = tc.SAFE_ROUTE_TIME_MULT if route == "safe" else 1.0
    return cells * part_value(cart, "horses") * mult


def cell_ambush(x: int, y: int, guard: float) -> float:
    from services import mount_service

    if mount_service._is_safe_cell(x, y):
        return 0.0
    per_cell = 1 - (1 - tc.CART_TRIP_AMBUSH) ** (1 / tc.AMBUSH_REF_CELLS)
    return min(per_cell * tc.CART_RING_MULT[grid.ring_tier(x, y)] * guard, 0.5)


def ambush_chance(cart: TradeCart, cells: list[tuple[int, int]]) -> float:
    """Шанс хотя бы одного нападения за путь - для подсказки игроку."""
    guard = part_value(cart, "guard")
    safe = 1.0
    for x, y in cells[:-1]:
        safe *= 1 - cell_ambush(x, y, guard)
    return 1 - safe


def roll_ambushes(cart: TradeCart, cells: list[tuple[int, int]], rng: random.Random) -> int:
    guard = part_value(cart, "guard")
    return sum(rng.random() < cell_ambush(x, y, guard) for x, y in cells[:-1])


def position(cart: TradeCart, now: datetime | None = None) -> tuple[int, int]:
    """Где повозка сейчас (для карты): в пути - по доле прошедшего времени."""
    if cart.status != "traveling" or cart.to_city is None:
        return wc.CITY_COORDS[cart.city]
    now = now or _now()
    cells = path(cart.city, cart.to_city, cart.route or "short")
    total = (_aware(cart.arrives_at) - _aware(cart.departed_at)).total_seconds()
    done = (now - _aware(cart.departed_at)).total_seconds()
    share = min(max(done / total, 0.0), 1.0) if total > 0 else 1.0
    index = min(int(share * len(cells)), len(cells)) - 1
    return cells[index] if index >= 0 else wc.CITY_COORDS[cart.city]


# --- Отправка ---


def _good(good_id) -> tc.Good:
    good = tc.GOODS_BY_ID.get(good_id) if isinstance(good_id, str) else None
    if good is None:
        raise TradeError("Такого товара нет.")
    return good


@dataclass
class Dispatch:
    cart: TradeCart
    cost: int
    crates: int
    seconds: float


async def dispatch(
    db: AsyncSession, character: Character, slot, to_city, route, goods,
    rng: random.Random | None = None, now: datetime | None = None,
) -> Dispatch:
    """Закупка в городе повозки и отправка в to_city. goods - {good_id: ящиков}
    (может быть пусто - перегнать повозку порожняком)."""
    rng = rng or random.Random()
    now = now or _now()
    firm = await require_firm(db, character)
    cart = await get_cart(db, character.id, slot)
    _require_idle(cart)
    if to_city not in fc.CITIES:
        raise TradeError("Нет такого города.")
    if to_city == cart.city:
        raise TradeError("Повозка уже в этом городе.")
    if route not in tc.ROUTES:
        raise TradeError("Выбери путь.")
    if cart.durability <= 0:
        raise TradeError("Обшивка выбита - сначала почини повозку.")
    if not isinstance(goods, dict):
        raise TradeError("Неверный заказ.")
    order: list[tuple[tc.Good, int]] = []
    for good_id, count in goods.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise TradeError("Неверное число ящиков.")
        if count == 0:
            continue
        good = _good(good_id)
        if good.city != cart.city:
            raise TradeError(f"{good.name} здесь не производят.")
        if firm.trade_level < tc.TIER_MIN_TRADE_LEVEL[good.tier]:
            raise TradeError(
                f"{tc.TIER_NAMES[good.tier].capitalize()} товар - с {tc.TIER_MIN_TRADE_LEVEL[good.tier]} уровня торговли."
            )
        order.append((good, count))
    total_crates = sum(n for _, n in order)
    if total_crates > capacity(cart):
        raise TradeError(f"В кузов влезет {capacity(cart)} ящ.")

    cargo: dict[str, int] = {}
    paid: dict[str, int] = {}
    total = 0
    for good, count in order:
        row = await market_row(db, cart.city, good.id, lock=True, now=now)
        cost = 0
        for _ in range(count):
            cost += city_buy_price(cart.city, good, row.pressure)
            row.pressure += tc.SATURATION_PER_CRATE
        cargo[good.id], paid[good.id] = count, cost
        total += cost
    if total:
        try:
            await wallet_service.charge(db, character.id, "farm", total)
        except wallet_service.NotEnoughCurrency:
            raise TradeError(f"Не хватает золота: закупка стоит {total}.") from None

    cells = path(cart.city, to_city, route)
    event = roll_event(route, total_crates, rng)
    seconds = trip_seconds(cart, len(cells), route) * (event.time_mult if event else 1.0)
    cart.cargo, cart.paid = cargo, paid
    cart.status, cart.to_city, cart.route = "traveling", to_city, route
    cart.departed_at, cart.arrives_at = now, now + timedelta(seconds=seconds)
    cart.ambushes = roll_ambushes(cart, cells, rng)
    cart.event = event.id if event else None
    await db.flush()
    return Dispatch(cart, total, total_crates, seconds)


def roll_event(route: str, crates_count: int, rng: random.Random) -> tc.TripEvent | None:
    """Событие в пути (или ничего). На безопасном пути плохие - вдвое реже;
    события с ящиками - только если есть груз."""
    if rng.random() >= tc.TRIP_EVENT_CHANCE:
        return None
    pool, weights = [], []
    for event in tc.TRIP_EVENTS:
        if event.crates and not crates_count:
            continue
        pool.append(event)
        weights.append(1.0 if event.good or route != "safe" else 0.5)
    return rng.choices(pool, weights)[0]


# --- Срочные заказы ---


def order_price(order: TradeOrder, level: int) -> int:
    """Цена ящика по заказу: цена города без насыщения x наценка заказа,
    с бонусом уровня торговли."""
    good = tc.GOODS_BY_ID[order.good_id]
    return round(city_sell_price(order.city, good, 0.0) * tc.ORDER_PRICE_MULT * (1 + tc.sell_bonus(level)))


async def active_orders(db: AsyncSession, now: datetime | None = None) -> list[TradeOrder]:
    now = _aware(now or _now())
    return list((await db.scalars(
        select(TradeOrder).where(TradeOrder.expires_at > now, TradeOrder.left > 0).order_by(TradeOrder.id)
    )).all())


async def order_tick(db: AsyncSession, rng: random.Random | None = None, now: datetime | None = None) -> TradeOrder | None:
    """Раз в ORDER_CHECK_MINUTES: если заказов меньше предела и с прошлого
    прошло ORDER_MIN_GAP_HOURS - с шансом появляется новый."""
    rng = rng or random.Random()
    now = _aware(now or _now())
    if len(await active_orders(db, now)) >= tc.ORDER_MAX_ACTIVE:
        return None
    last = await db.scalar(select(func.max(TradeOrder.created_at)))
    if last is not None and now - _aware(last) < timedelta(hours=tc.ORDER_MIN_GAP_HOURS):
        return None
    if rng.random() >= tc.ORDER_SPAWN_CHANCE:
        return None
    return await spawn_order(db, rng, now)


async def spawn_order(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> TradeOrder:
    now = _aware(now or _now())
    busy = {(o.city, o.good_id) for o in await active_orders(db, now)}
    goods = [g for g in tc.GOODS]
    good = rng.choices(goods, [tc.ORDER_TIER_WEIGHTS[g.tier] for g in goods])[0]
    cities = [c for c in fc.CITIES if c != good.city and (c, good.id) not in busy] or [
        c for c in fc.CITIES if c != good.city
    ]
    count = rng.randint(*tc.ORDER_CRATES)
    order = TradeOrder(
        city=rng.choice(cities), good_id=good.id, total=count, left=count,
        created_at=now, expires_at=now + timedelta(hours=tc.ORDER_HOURS),
    )
    db.add(order)
    await db.flush()
    return order


def order_text(order: TradeOrder) -> str:
    good = tc.GOODS_BY_ID[order.good_id]
    return (
        f"📜 Срочный заказ: {city_title(order.city)} нужно {order.total} ящ. «{good.name}» "
        f"({tc.TIER_NAMES[good.tier]}), цена +{round((tc.ORDER_PRICE_MULT - 1) * 100)}%, "
        f"на {tc.ORDER_HOURS} ч. Кто довёз первым - тот и получил. Вкладка «Фракция»."
    )


async def order_subscribers(db: AsyncSession) -> list[int]:
    """Персонажи, включившие вести о заказах."""
    return list((await db.scalars(
        select(TradeFirm.character_id).where(TradeFirm.notify_orders.is_(True), TradeFirm.name.is_not(None))
    )).all())


# --- Прибытие ---


def _lose(cart: TradeCart, share: float, rng: random.Random) -> dict[str, int]:
    """Теряет долю ящиков (с округлением вверх), случайно по товарам."""
    cargo = dict(cart.cargo or {})
    paid = dict(cart.paid or {})
    total = sum(cargo.values())
    n = min(math.ceil(total * share), total)
    lost: dict[str, int] = {}
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


@dataclass
class Arrival:
    character_id: int
    slot: int
    firm_name: str
    to_city: str
    notify: bool = True
    crates: int = 0
    revenue: int = 0
    profit: int = 0
    ambushes: int = 0
    broke: bool = False
    lost: dict = field(default_factory=dict)
    durability: int = 0
    max_durability: int = 0
    chests: int = 0
    level_up: int | None = None
    prosperity: int = 0
    char_levelup: object = None
    event: str | None = None
    order_crates: int = 0
    toll: int = 0

    def text(self) -> str:
        lines = [f"🐂 Повозка №{self.slot} фирмы «{self.firm_name}» прибыла в {city_title(self.to_city)}."]
        if self.crates:
            lines.append(f"💰 Продано {self.crates} ящ. за {self.revenue} золота, прибыль {self.profit:+d}.")
        if self.order_crates:
            lines.append(f"📜 По срочному заказу ушло {self.order_crates} ящ.")
        if self.event:
            lines.append(f"🛤 {tc.TRIP_EVENTS_BY_ID[self.event].text}")
        if self.ambushes:
            lines.append(f"⚔ В пути напали {self.ambushes} раз(а), обшивка {self.durability}/{self.max_durability}.")
        if self.lost:
            lines.append(f"💥 Обшивка выбита, рассыпалось: {lost_text(self.lost)}.")
        if self.chests:
            lines.append(f"🎁 В ящиках нашёлся Пепельный ларец ×{self.chests}!")
        if self.level_up:
            lines.append(f"📈 Уровень торговли: {self.level_up}!")
        if self.char_levelup is not None and getattr(self.char_levelup, "xp_awarded", 0):
            lines.append(f"✨ +{self.char_levelup.xp_awarded} опыта.")
        return "\n".join(lines)


async def arrive(
    db: AsyncSession, cart: TradeCart, rng: random.Random | None = None, now: datetime | None = None,
) -> Arrival:
    """Повозка доехала: нападения бьют по обшивке, груз продаётся по цене
    на месте, опыт, ларцы, процветание родного города торговца."""
    rng = rng or random.Random()
    now = _aware(now or _now())
    character = await db.get(Character, cart.character_id)
    firm = await get_firm(db, cart.character_id, lock=True)
    out = Arrival(cart.character_id, cart.slot, firm.name or "", cart.to_city, notify=firm.notify_arrival)
    out.ambushes = cart.ambushes or 0
    for _ in range(out.ambushes):
        if cart.durability > 0:
            cart.durability -= 1
            if cart.durability > 0:
                continue
        out.broke = True
        for good_id, n in _lose(cart, tc.LOSS_ON_BREAK, rng).items():
            out.lost[good_id] = out.lost.get(good_id, 0) + n
    out.durability, out.max_durability = cart.durability, max_durability(cart)
    event = tc.TRIP_EVENTS_BY_ID.get(cart.event or "")
    out.event = event.id if event else None
    if event is not None and event.crates and cart.cargo:
        cargo, paid = dict(cart.cargo), dict(cart.paid or {})
        good_id = rng.choice(sorted(cargo))
        if event.crates > 0:
            cargo[good_id] += event.crates  # брошенный ящик - бесплатный
        else:
            per = paid.get(good_id, 0) / cargo[good_id]
            cargo[good_id] -= 1
            paid[good_id] = round(paid.get(good_id, 0) - per)
            if cargo[good_id] <= 0:
                cargo.pop(good_id)
                paid.pop(good_id, None)
        cart.cargo, cart.paid = cargo, paid

    revenue = cost = raw = 0
    level = firm.trade_level
    for good_id, count in (cart.cargo or {}).items():
        good = tc.GOODS_BY_ID[good_id]
        # Сначала - срочный заказ на этот товар здесь, если он ещё открыт.
        order = await db.scalar(
            select(TradeOrder).where(
                TradeOrder.city == cart.to_city, TradeOrder.good_id == good_id,
                TradeOrder.left > 0, TradeOrder.expires_at > now,
            ).order_by(TradeOrder.id).limit(1).with_for_update().execution_options(populate_existing=True)
        )
        by_order = min(order.left, count) if order is not None else 0
        if by_order:
            order.left -= by_order
            revenue += order_price(order, level) * by_order
            out.order_crates += by_order
            raw += fc.POINTS_PER_CRATE[good.tier] * by_order * (tc.ORDER_PROSPERITY_MULT - 1)
        row = await market_row(db, cart.to_city, good_id, lock=True, now=now)
        for _ in range(count - by_order):
            revenue += round(city_sell_price(cart.to_city, good, row.pressure) * (1 + tc.sell_bonus(level)))
            row.pressure += tc.SATURATION_PER_CRATE
        cost += (cart.paid or {}).get(good_id, 0)
        out.crates += count
        firm.trade_xp += tc.XP_PER_CRATE[good.tier] * count
        raw += fc.POINTS_PER_CRATE[good.tier] * count
        for _ in range(count):
            if rng.random() < tc.CHEST_CHANCE_PER_CRATE[good.tier]:
                out.chests += 1
    if event is not None and revenue:
        revenue = round(revenue * event.revenue_mult)
        out.toll = min(event.toll, revenue)
        revenue -= out.toll
    out.revenue, out.profit = revenue, revenue - cost
    if revenue:
        await wallet_service.deposit(db, character.id, "farm", revenue)
    firm.profit_total += max(out.profit, 0)
    while firm.trade_xp >= tc.xp_to_next(firm.trade_level):
        firm.trade_xp -= tc.xp_to_next(firm.trade_level)
        firm.trade_level += 1
        out.level_up = firm.trade_level
    for _ in range(out.chests):
        await lootbox_service.grant_chest(db, character, 0)
    if out.crates:
        from services import experience_service

        out.char_levelup = await experience_service.grant_activity_xp(db, character, "crate", out.crates)
        out.prosperity = await faction_service.contribute(db, character, level, raw, now)

    db.add(TradeTrip(
        character_id=cart.character_id, slot=cart.slot, from_city=cart.city, to_city=cart.to_city,
        route=cart.route or "short", crates=out.crates, revenue=revenue, profit=out.profit,
        ambushes=out.ambushes, lost=out.lost, event=out.event, order_crates=out.order_crates, arrived_at=now,
    ))
    cart.city = cart.to_city
    cart.status, cart.to_city, cart.route = "idle", None, None
    cart.departed_at = cart.arrives_at = None
    cart.ambushes = 0
    cart.event = None
    cart.cargo, cart.paid = {}, {}
    await db.flush()
    return out


async def tick(db: AsyncSession, rng: random.Random | None = None, now: datetime | None = None) -> list[Arrival]:
    """Все повозки, чьё время прибытия подошло. Строки берутся с SKIP LOCKED:
    второй одновременный тик их не тронет."""
    now = _aware(now or _now())
    due = (await db.scalars(
        select(TradeCart).where(TradeCart.status == "traveling", TradeCart.arrives_at <= now)
        .order_by(TradeCart.arrives_at).limit(50)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True)
    )).all()
    return [await arrive(db, cart, rng, now) for cart in due]


async def recent_trips(db: AsyncSession, character_id: int, limit: int = 20) -> list[TradeTrip]:
    return list((await db.scalars(
        select(TradeTrip).where(TradeTrip.character_id == character_id)
        .order_by(TradeTrip.arrived_at.desc(), TradeTrip.id.desc()).limit(limit)
    )).all())
