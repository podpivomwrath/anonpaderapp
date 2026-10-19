"""Курьер (2026-10-19): доставка вещей, зелий и руды на расстояние.

Посылка списывается у отправителя при подтверждении (transfer_service.take)
и лежит в courier_deliveries, пока курьер не отдаст её (transfer_service.give).
Курьер выходит из родного города отправителя и бежит по клеткам: сначала к
отправителю за посылкой, потом к получателю. Цель берётся там, где персонаж
стоит в момент шага, - ушёл с клетки, курьер поворачивает прямо в дороге.

Сервис не шлёт сообщений: advance() возвращает, что случилось, говорит
bot/handlers/courier.py. Числа - game/economy/courier_config.py.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import courier_config as cc
from game.world import grid
from game.world import world_config as wc
from models import Character, CourierDelivery
from services import transfer_service, wallet_service

ACTIVE, DELIVERED, RETURNED = "active", "delivered", "returned"
PICKUP, DELIVER = "pickup", "deliver"


class CourierError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --- Покупка ------------------------------------------------------------------


async def buy(db: AsyncSession, character: Character) -> None:
    if character.has_courier:
        raise CourierError("Курьер у тебя уже есть.")
    try:
        await wallet_service.charge(db, character.id, "donate", cc.PRICE)
    except wallet_service.NotEnoughCurrency:
        raise CourierError(f"Не хватает самоцветов: нужно 💎{cc.PRICE}.") from None
    character.has_courier = True
    await db.flush()


# --- Доставка -----------------------------------------------------------------


async def active_of(db: AsyncSession, sender_id: int) -> CourierDelivery | None:
    return await db.scalar(select(CourierDelivery).where(
        CourierDelivery.sender_id == sender_id, CourierDelivery.status == ACTIVE,
    ))


async def incoming(db: AsyncSession, recipient_id: int) -> list[CourierDelivery]:
    return list((await db.scalars(select(CourierDelivery).where(
        CourierDelivery.recipient_id == recipient_id, CourierDelivery.status == ACTIVE,
        CourierDelivery.phase == DELIVER,
    ))).all())


def start_cell(sender: Character) -> tuple[int, int]:
    """Курьер живёт в родном городе отправителя."""
    return wc.CITY_COORDS.get(sender.region or "", (sender.pos_x, sender.pos_y))


async def send(
    db: AsyncSession, sender: Character, recipient: Character, offer: "transfer_service.Offer",
    amount: int, reveal_sender: bool, now: datetime | None = None,
) -> CourierDelivery:
    """Отдать посылку курьеру: списать у отправителя и выпустить курьера.
    CourierError / transfer_service.TransferFailed - ничего не списано."""
    if not sender.has_courier:
        raise CourierError("Курьера у тебя нет.")
    if offer.kind not in transfer_service.NEEDS_NEAR:
        raise CourierError("Это передаётся и без курьера.")
    if await active_of(db, sender.id) is not None:
        raise CourierError("Курьер ещё бегает с прошлой посылкой. Дождись, пока он её отдаст.")
    amount = await transfer_service.take(db, sender.id, offer, amount)
    x, y = start_cell(sender)
    delivery = CourierDelivery(
        sender_id=sender.id, recipient_id=recipient.id, kind=offer.kind, ref=offer.ref,
        label=offer.label[:160], amount=amount, reveal_sender=reveal_sender,
        phase=PICKUP, status=ACTIVE, x=x, y=y, last_step_at=now or _now(), waiting=False,
    )
    db.add(delivery)
    await db.flush()
    return delivery


def next_cell(x: int, y: int, tx: int, ty: int) -> tuple[int, int]:
    """Шаг в соседнюю клетку к цели (по прямой, как маунт)."""
    path = grid.line_path(x, y, tx, ty)
    return path[0] if path else (x, y)


@dataclass
class Event:
    #: picked | waiting | delivered | returned
    kind: str
    delivery: CourierDelivery


async def advance(db: AsyncSession, busy_ids: set[int], now: datetime | None = None) -> list[Event]:
    """Шаги всех курьеров до текущего момента. busy_ids - персонажи в бою или
    рейде (это знает только бот): им посылку не отдают, курьер ждёт рядом."""
    now = now or _now()
    step = timedelta(seconds=cc.SECONDS_PER_CELL)
    events: list[Event] = []
    rows = (await db.scalars(
        select(CourierDelivery).where(CourierDelivery.status == ACTIVE)
        .with_for_update().execution_options(populate_existing=True)
    )).all()
    for d in rows:
        target_id = d.sender_id if d.phase == PICKUP else d.recipient_id
        target = await db.get(Character, target_id) if target_id is not None else None
        if target is None:
            events += await _lost_target(db, d, now)
            continue
        goal = (target.pos_x, target.pos_y)
        last = _aware(d.last_step_at)
        steps = int((now - last) / step)
        for _ in range(steps):
            if (d.x, d.y) == goal:
                break
            d.x, d.y = next_cell(d.x, d.y, *goal)
        d.last_step_at = last + steps * step
        if (d.x, d.y) != goal:
            d.waiting = False
            continue
        # На месте: не копить шаги, пока стоит.
        d.last_step_at = now
        if d.phase == PICKUP:
            d.phase = DELIVER
            events.append(Event("picked", d))
            continue
        if target.id in busy_ids:
            if not d.waiting:
                d.waiting = True
                events.append(Event("waiting", d))
            continue
        await transfer_service.give(db, target.id, d.kind, d.ref, d.amount)
        transfer_service.log(db, d.sender_id, target.id, d.kind, d.ref, d.label, d.amount)
        d.status, d.finished_at, d.waiting = DELIVERED, now, False
        events.append(Event("delivered", d))
    await db.flush()
    return events


async def _lost_target(db: AsyncSession, d: CourierDelivery, now: datetime) -> list[Event]:
    """Персонажа удалили, пока курьер бежал: посылку - обратно отправителю."""
    if d.sender_id is not None and await db.get(Character, d.sender_id) is not None:
        await transfer_service.give(db, d.sender_id, d.kind, d.ref, d.amount)
    d.status, d.finished_at = RETURNED, now
    return [Event("returned", d)]
