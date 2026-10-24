"""Рынок (2026-10-23): заявки на товары («офферы») и витрина снаряжения.

Товары - руда, травы, еда, расходники ремёсел, ларцы (каталог - в
game/economy/market_config.py). Продавец ставит «продам N по цене», покупатель
- «куплю N по цене»; сходятся цены - сделка проходит сама, по цене той
заявки, что стояла раньше (её автор её и назначил). Витрина - некованые
уникальные вещи по фиксированной цене, без заявок на покупку.

Деньги и товар уходят на рынок сразу при выставлении: продавец отдаёт товар,
покупатель - золото на всё количество. Так сделке нечего ждать: у обеих
сторон всё уже лежит на рынке. Купленное попадает в «ящик» и забирается в
любом городе; выручка приходит сразу. Комиссии - за выставление и с выручки
продавца, обе - в казну фракции (faction_service.pay_tax).

Поиск встречных заявок по товару - под одной на товар блокировкой Postgres:
две встречные заявки, пришедшие в одну секунду, иначе обе встали бы в стакан,
не увидев друг друга.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import market_config as mc
from models import (
    Character,
    CharacterCraftGear,
    CharacterFood,
    CharacterHerb,
    CharacterLootbox,
    CharacterOre,
    Inventory,
    Item,
    MarketInbox,
    MarketOrder,
    MarketTrade,
)
from services import item_service, premium_service, wallet_service
from services.transfer_service import _credit_stack, _take_stack

OPEN, FILLED, CANCELLED, EXPIRED = "open", "filled", "cancelled", "expired"
SELL, BUY = "sell", "buy"


class MarketError(Exception):
    """Отказ с готовым текстом для игрока."""


@dataclass
class Notice:
    character_id: int
    text: str


@dataclass
class Result:
    order: MarketOrder | None = None
    notices: list[Notice] = field(default_factory=list)
    #: сколько исполнилось сразу и за сколько золота
    filled: int = 0
    gold: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


# --- Названия -----------------------------------------------------------------------


async def label(db: AsyncSession, key: str) -> str:
    if key.startswith("item:"):
        item = await db.get(Item, int(key.split(":", 1)[1]))
        return item_service.format_item_label(item) if item is not None else "вещь"
    good = mc.good(key)
    return f"{good.emoji} {good.name}" if good else key


# --- Товар у игрока -----------------------------------------------------------------


def _stack(key: str, character_id: int):
    """(модель, ключ строки) для стакающегося товара."""
    kind, _, rest = key.partition(":")
    if kind == "ore":
        ore_id, grade = rest.split(":", 1)
        return CharacterOre, {"character_id": character_id, "ore_id": ore_id, "grade": grade}
    if kind == "herb":
        return CharacterHerb, {"character_id": character_id, "herb_id": rest}
    if kind == "food":
        dish_id, grade = rest.split(":", 1)
        return CharacterFood, {"character_id": character_id, "dish_id": dish_id, "grade": grade}
    if kind == "craft":
        return CharacterCraftGear, {"character_id": character_id, "tool_id": rest}
    return None, None


async def holdings(db: AsyncSession, character_id: int) -> dict[str, int]:
    """Что игрок может выставить на продажу: ключ товара -> количество."""
    out: dict[str, int] = {}
    for ore_id, grade, count in (await db.execute(select(CharacterOre.ore_id, CharacterOre.grade, CharacterOre.count)
                                                  .where(CharacterOre.character_id == character_id))).all():
        out[f"ore:{ore_id}:{grade}"] = count
    for herb_id, count in (await db.execute(select(CharacterHerb.herb_id, CharacterHerb.count)
                                            .where(CharacterHerb.character_id == character_id))).all():
        out[f"herb:{herb_id}"] = count
    for dish_id, grade, count in (await db.execute(select(CharacterFood.dish_id, CharacterFood.grade, CharacterFood.count)
                                                   .where(CharacterFood.character_id == character_id))).all():
        out[f"food:{dish_id}:{grade}"] = count
    for tool_id, count in (await db.execute(select(CharacterCraftGear.tool_id, CharacterCraftGear.count).where(
        CharacterCraftGear.character_id == character_id, CharacterCraftGear.tool_id.in_(mc.CRAFT_GOODS),
    ))).all():
        out[f"craft:{tool_id}"] = count
    for kind, count in (await db.execute(
        select(CharacterLootbox.kind, func.count()).where(
            CharacterLootbox.character_id == character_id, CharacterLootbox.status == "closed",
        ).group_by(CharacterLootbox.kind)
    )).all():
        out[f"chest:{kind or 'ashen'}"] = count
    return {k: v for k, v in out.items() if v > 0 and k in mc.goods()}


async def _take(db: AsyncSession, character_id: int, key: str, qty: int) -> bool:
    model, row_key = _stack(key, character_id)
    if model is not None:
        return await _take_stack(db, model, row_key, qty)
    if key.startswith("chest:"):
        kind = key.split(":", 1)[1]
        ids = (await db.scalars(
            select(CharacterLootbox.id).where(
                CharacterLootbox.character_id == character_id, CharacterLootbox.status == "closed",
                CharacterLootbox.kind == kind,
            ).order_by(CharacterLootbox.id).limit(qty).with_for_update(skip_locked=True)
        )).all()
        if len(ids) < qty:
            return False
        await db.execute(delete(CharacterLootbox).where(CharacterLootbox.id.in_(ids))
                         .execution_options(synchronize_session="fetch"))
        return True
    return False


async def _give(db: AsyncSession, character_id: int, key: str, qty: int) -> None:
    model, row_key = _stack(key, character_id)
    if model is not None:
        await _credit_stack(db, model, row_key, qty)
    elif key.startswith("chest:"):
        kind = key.split(":", 1)[1]
        for _ in range(qty):
            db.add(CharacterLootbox(character_id=character_id, status="closed", kind=kind, streak=None))
    elif key.startswith("item:"):
        db.add(Inventory(character_id=character_id, item_id=int(key.split(":", 1)[1]), equipped=False))
    await db.flush()


def sellable_item(item: Item, equipped: bool) -> bool:
    """На витрину - только некованая уникальная вещь, не надетая."""
    return (
        not equipped and item.rarity == item_service.UNIQUE_RARITY_ID
        and not item.bound and item.craft_spec is None
    )


async def sellable_items(db: AsyncSession, character_id: int) -> list[Item]:
    return [item for item, equipped in await item_service.get_inventory(db, character_id)
            if sellable_item(item, equipped)]


# --- Деньги ------------------------------------------------------------------------


async def _charge(db: AsyncSession, character_id: int, amount: int, reason: str) -> None:
    try:
        await wallet_service.charge(db, character_id, "farm", amount, reason=reason)
    except wallet_service.NotEnoughCurrency:
        raise MarketError(f"Не хватает золота: нужно {money(amount)}.") from None


async def _fee(db: AsyncSession, character_id: int, gross: int) -> int:
    """Комиссия за выставление: списать и отдать в казну фракции."""
    from services import faction_service

    fee = max(1, round(gross * mc.LISTING_FEE))
    await _charge(db, character_id, fee, "market.listing_fee")
    await faction_service.pay_tax(db, character_id, "farm", fee)
    return fee


async def _pay_seller(db: AsyncSession, seller_id: int, gross: int) -> int:
    """Выручка продавцу за вычетом комиссии (она - в казну фракции)."""
    from services import faction_service

    fee = round(gross * mc.SALE_FEE)
    net = gross - fee
    if net > 0:
        await wallet_service.deposit(db, seller_id, "farm", net, reason="market.sale")
    await faction_service.pay_tax(db, seller_id, "farm", fee)
    return net


async def _refund(db: AsyncSession, character_id: int, amount: int) -> None:
    if amount > 0:
        await wallet_service.deposit(db, character_id, "farm", amount, taxable=False, reason="market.refund")


# --- Заявки ------------------------------------------------------------------------


async def _lock_good(db: AsyncSession, key: str) -> None:
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("select pg_advisory_xact_lock(:k)"), {"k": zlib.crc32(key.encode()) & 0x7FFFFFFF})


async def open_count(db: AsyncSession, character_id: int) -> int:
    return await db.scalar(select(func.count()).select_from(MarketOrder).where(
        MarketOrder.character_id == character_id, MarketOrder.status == OPEN,
    )) or 0


def limit_for(character: Character) -> int:
    return mc.MAX_ORDERS_PREMIUM if premium_service.is_premium(character) else mc.MAX_ORDERS


async def _validate(db: AsyncSession, character: Character, qty: int, price: int) -> None:
    if not isinstance(qty, int) or not isinstance(price, int) or qty < 1 or price < 1:
        raise MarketError("Количество и цена - целые числа больше нуля.")
    if qty > mc.MAX_QTY or price > mc.MAX_PRICE:
        raise MarketError("Слишком большое число.")
    if qty * price < mc.MIN_ORDER_GOLD:
        raise MarketError(f"Заявка - от {mc.MIN_ORDER_GOLD} золота (цена × количество).")
    if await open_count(db, character.id) >= limit_for(character):
        raise MarketError(f"Открытых заявок не больше {limit_for(character)}. Сними или дождись старых.")


def _new_order(character_id: int, side: str, key: str, qty: int, price: int, now: datetime) -> MarketOrder:
    return MarketOrder(
        character_id=character_id, side=side, good=key, price=price, qty_total=qty, qty_left=qty,
        status=OPEN, created_at=now, expires_at=now + timedelta(hours=mc.ORDER_HOURS),
    )


async def _trade(db, key: str, price: int, qty: int, buyer_id: int, seller_id: int, now: datetime) -> None:
    db.add(MarketTrade(good=key, price=price, qty=qty, buyer_id=buyer_id, seller_id=seller_id, created_at=now))
    db.add(MarketInbox(character_id=buyer_id, good=key, qty=qty, created_at=now))


async def place_sell(db: AsyncSession, character: Character, key: str, qty: int, price: int,
                     now: datetime | None = None) -> Result:
    now = now or _now()
    if mc.good(key) is None:
        raise MarketError("Такой товар на рынке не продают.")
    await _validate(db, character, qty, price)
    await _fee(db, character.id, qty * price)
    if not await _take(db, character.id, key, qty):
        raise MarketError("Столько у тебя нет.")
    await _lock_good(db, key)
    order = _new_order(character.id, SELL, key, qty, price, now)
    db.add(order)
    result = Result(order=order)
    name = await label(db, key)
    buys = (await db.scalars(
        select(MarketOrder).where(
            MarketOrder.good == key, MarketOrder.side == BUY, MarketOrder.status == OPEN,
            MarketOrder.price >= price, MarketOrder.character_id != character.id,
        ).order_by(MarketOrder.price.desc(), MarketOrder.id).with_for_update()
    )).all()
    for buy in buys:
        if order.qty_left <= 0:
            break
        q = min(order.qty_left, buy.qty_left)
        gross = q * buy.price
        net = await _pay_seller(db, character.id, gross)
        await _trade(db, key, buy.price, q, buy.character_id, character.id, now)
        order.qty_left -= q
        buy.qty_left -= q
        if buy.qty_left == 0:
            buy.status = FILLED
        result.filled += q
        result.gold += net
        result.notices.append(Notice(
            buy.character_id, f"🛒 Рынок: куплено {name} ×{q} по {money(buy.price)}. Забрать - в любом городе.",
        ))
    if order.qty_left == 0:
        order.status = FILLED
    if result.filled:
        result.notices.append(Notice(
            character.id, f"💰 Рынок: продано {name} ×{result.filled}, +{money(result.gold)} золота.",
        ))
    await db.flush()
    return result


async def place_buy(db: AsyncSession, character: Character, key: str, qty: int, price: int,
                    now: datetime | None = None) -> Result:
    now = now or _now()
    if mc.good(key) is None:
        raise MarketError("Такой товар на рынке не продают.")
    await _validate(db, character, qty, price)
    await _fee(db, character.id, qty * price)
    await _charge(db, character.id, qty * price, "market.buy_order")
    await _lock_good(db, key)
    order = _new_order(character.id, BUY, key, qty, price, now)
    db.add(order)
    result = Result(order=order)
    name = await label(db, key)
    sells = (await db.scalars(
        select(MarketOrder).where(
            MarketOrder.good == key, MarketOrder.side == SELL, MarketOrder.status == OPEN,
            MarketOrder.price <= price, MarketOrder.character_id != character.id,
        ).order_by(MarketOrder.price, MarketOrder.id).with_for_update()
    )).all()
    spent = 0
    for sell in sells:
        if order.qty_left <= 0:
            break
        q = min(order.qty_left, sell.qty_left)
        net = await _pay_seller(db, sell.character_id, q * sell.price)
        await _trade(db, key, sell.price, q, character.id, sell.character_id, now)
        order.qty_left -= q
        sell.qty_left -= q
        if sell.qty_left == 0:
            sell.status = FILLED
        spent += q * sell.price
        result.filled += q
        result.notices.append(Notice(
            sell.character_id, f"💰 Рынок: продано {name} ×{q}, +{money(net)} золота.",
        ))
    if result.filled:
        # Купил дешевле своей цены - разница сразу назад.
        await _refund(db, character.id, result.filled * price - spent)
        result.gold = spent
        result.notices.append(Notice(
            character.id, f"🛒 Рынок: куплено {name} ×{result.filled} за {money(spent)}. Забрать - в любом городе.",
        ))
    if order.qty_left == 0:
        order.status = FILLED
    await db.flush()
    return result


async def list_item(db: AsyncSession, character: Character, item_id: int, price: int,
                    now: datetime | None = None) -> Result:
    """Выставить вещь на витрину."""
    now = now or _now()
    await _validate(db, character, 1, price)
    item = await db.get(Item, item_id)
    entry = await item_service.get_inventory_entry(db, character.id, item_id)
    if item is None or entry is None or not sellable_item(item, entry.equipped):
        raise MarketError("На витрину - только некованая уникальная вещь, и не надетая.")
    await _fee(db, character.id, price)
    moved = await db.execute(delete(Inventory).where(
        Inventory.item_id == item_id, Inventory.character_id == character.id, Inventory.equipped.is_(False),
    ).execution_options(synchronize_session="fetch"))
    if not moved.rowcount:
        raise MarketError("Этой вещи у тебя уже нет.")
    from services import resource_log

    resource_log.add(db, character.id, "item", str(item_id), -1)
    order = _new_order(character.id, SELL, f"item:{item_id}", 1, price, now)
    db.add(order)
    await db.flush()
    return Result(order=order)


async def buy_item(db: AsyncSession, character: Character, order_id: int, now: datetime | None = None) -> Result:
    now = now or _now()
    order = await db.get(MarketOrder, order_id, with_for_update=True)
    if order is None or order.status != OPEN or not order.good.startswith("item:"):
        raise MarketError("Эту вещь уже купили или сняли с витрины.")
    if order.character_id == character.id:
        raise MarketError("Это твой же лот.")
    await _charge(db, character.id, order.price, "market.buy_item")
    net = await _pay_seller(db, order.character_id, order.price)
    await _trade(db, order.good, order.price, 1, character.id, order.character_id, now)
    order.qty_left = 0
    order.status = FILLED
    name = await label(db, order.good)
    await db.flush()
    return Result(order=order, filled=1, gold=order.price, notices=[
        Notice(order.character_id, f"💰 Рынок: продано {name}, +{money(net)} золота."),
        Notice(character.id, f"🛒 Рынок: куплено {name} за {money(order.price)}. Забрать - в любом городе."),
    ])


async def _close(db: AsyncSession, order: MarketOrder, status: str) -> None:
    """Снять заявку: остаток товара - продавцу в сумку, золото - покупателю."""
    if order.qty_left > 0:
        if order.side == SELL:
            await _give(db, order.character_id, order.good, order.qty_left)
        else:
            await _refund(db, order.character_id, order.qty_left * order.price)
    order.status = status
    await db.flush()


async def cancel(db: AsyncSession, character: Character, order_id: int) -> MarketOrder:
    order = await db.get(MarketOrder, order_id, with_for_update=True)
    if order is None or order.character_id != character.id or order.status != OPEN:
        raise MarketError("Этой заявки уже нет.")
    await _close(db, order, CANCELLED)
    return order


async def expire_due(db: AsyncSession, now: datetime | None = None) -> list[Notice]:
    now = now or _now()
    orders = (await db.scalars(
        select(MarketOrder).where(MarketOrder.status == OPEN, MarketOrder.expires_at <= now)
        .with_for_update(skip_locked=True)
    )).all()
    notices = []
    for order in orders:
        name = await label(db, order.good)
        left = order.qty_left
        await _close(db, order, EXPIRED)
        back = (f"{name} ×{left} - в сумке" if order.side == SELL
                else f"{money(left * order.price)} золота вернулось")
        what = "лот" if order.good.startswith("item:") else "заявка"
        notices.append(Notice(order.character_id, f"⌛ Рынок: {what} снят(а) по сроку - {back}."))
    return notices


# --- Ящик купленного -----------------------------------------------------------------


async def inbox(db: AsyncSession, character_id: int) -> list[MarketInbox]:
    return list((await db.scalars(
        select(MarketInbox).where(MarketInbox.character_id == character_id).order_by(MarketInbox.id)
    )).all())


async def claim(db: AsyncSession, character: Character) -> list[str]:
    """Забрать купленное - только в городе. Вернёт строки «что забрал»."""
    from game.world import grid

    if grid.city_region_at(character.pos_x, character.pos_y) is None:
        raise MarketError("Купленное забирают в городе - в любом.")
    rows = (await db.scalars(
        select(MarketInbox).where(MarketInbox.character_id == character.id).with_for_update()
    )).all()
    lines = []
    for row in rows:
        await _give(db, character.id, row.good, row.qty)
        lines.append(f"{await label(db, row.good)} ×{row.qty}")
        await db.delete(row)
    await db.flush()
    return lines


async def give_good(db: AsyncSession, character_id: int, key: str, qty: int) -> None:
    """Выдать товар рынка - для курьера, который принёс ящик."""
    await _give(db, character_id, key, qty)


async def send_courier(db: AsyncSession, character: Character) -> list[str]:
    """Купленное - курьером, где бы игрок ни был (2026-10-24, владелец).
    Ящик списывается сразу, товар отдаёт курьер (courier_service.send_market)."""
    from services import courier_service

    if not character.has_courier:
        raise MarketError("Курьера у тебя нет. Его покупают в Магазине.")
    if await courier_service.active_of(db, character.id) is not None:
        raise MarketError("Курьер ещё бегает с прошлой посылкой. Дождись, пока он её отдаст.")
    rows = (await db.scalars(
        select(MarketInbox).where(MarketInbox.character_id == character.id).with_for_update()
    )).all()
    if not rows:
        raise MarketError("Ящик пуст.")
    lines = [f"{await label(db, row.good)} ×{row.qty}" for row in rows]
    parts = [(row.good, row.qty) for row in rows]
    for row in rows:
        await db.delete(row)
    try:
        await courier_service.send_market(db, character, parts, ", ".join(lines))
    except courier_service.CourierError as exc:
        raise MarketError(str(exc)) from None
    await db.flush()
    return lines


# --- Обзор -------------------------------------------------------------------------


async def book(db: AsyncSession, key: str) -> dict:
    """Стакан: лучшие цены продажи и покупки с количеством на каждой цене."""
    async def side(s: str, order_by):
        return [(int(p), int(q)) for p, q in (await db.execute(
            select(MarketOrder.price, func.sum(MarketOrder.qty_left)).where(
                MarketOrder.good == key, MarketOrder.side == s, MarketOrder.status == OPEN,
            ).group_by(MarketOrder.price).order_by(order_by).limit(mc.BOOK_DEPTH)
        )).all()]
    return {"sells": await side(SELL, MarketOrder.price), "buys": await side(BUY, MarketOrder.price.desc())}


async def summary(db: AsyncSession) -> dict[str, dict]:
    """По товарам с живыми заявками или сделками: лучшие цены и последняя."""
    out: dict[str, dict] = {}
    for side, field_name, best in ((SELL, "sell", func.min), (BUY, "buy", func.max)):
        for key, price in (await db.execute(
            select(MarketOrder.good, best(MarketOrder.price)).where(
                MarketOrder.status == OPEN, MarketOrder.side == side,
            ).group_by(MarketOrder.good)
        )).all():
            out.setdefault(key, {})[field_name] = int(price)
    last_ids = select(func.max(MarketTrade.id)).group_by(MarketTrade.good)
    for key, price in (await db.execute(
        select(MarketTrade.good, MarketTrade.price).where(MarketTrade.id.in_(last_ids))
    )).all():
        out.setdefault(key, {})["last"] = int(price)
    return out


async def history(db: AsyncSession, key: str, days: int = 14) -> list[tuple[str, int, int]]:
    """(день, средняя цена, штук) за последние дни."""
    since = _now() - timedelta(days=days)
    rows = (await db.execute(
        select(MarketTrade.created_at, MarketTrade.price, MarketTrade.qty)
        .where(MarketTrade.good == key, MarketTrade.created_at >= since)
    )).all()
    by_day: dict[str, list[int]] = {}
    for at, price, qty in rows:
        day = at.date().isoformat()
        d = by_day.setdefault(day, [0, 0])
        d[0] += price * qty
        d[1] += qty
    return [(day, round(s / q), q) for day, (s, q) in sorted(by_day.items()) if q]


async def my_orders(db: AsyncSession, character_id: int) -> list[MarketOrder]:
    return list((await db.scalars(
        select(MarketOrder).where(MarketOrder.character_id == character_id, MarketOrder.status == OPEN)
        .order_by(MarketOrder.id.desc())
    )).all())


async def showcase(db: AsyncSession) -> list[MarketOrder]:
    return list((await db.scalars(
        select(MarketOrder).where(MarketOrder.status == OPEN, MarketOrder.good.like("item:%"))
        .order_by(MarketOrder.price)
    )).all())


async def my_trades(db: AsyncSession, character_id: int, limit: int = 20) -> list[MarketTrade]:
    return list((await db.scalars(
        select(MarketTrade).where(or_(MarketTrade.buyer_id == character_id, MarketTrade.seller_id == character_id))
        .order_by(MarketTrade.id.desc()).limit(limit)
    )).all())

