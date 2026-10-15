"""Заказы на игроков (2026-10-16). Правила - game/economy/contract_config.py.

Самоцветы заказчика списываются при создании заказа (атомарный кошелёк) и
уходят охотникам по одному убийству за раз; заказ закрывается, когда убийства
кончились, или сгорает через HOURS часов вместе с остатком.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import contract_config as cc
from game.world import grid
from models import Character, Contract, ContractTaker
from services import wallet_service


class ContractError(Exception):
    """Отказ с готовым текстом для игрока."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _active(now: datetime):
    return (Contract.status == "active", Contract.kills_left > 0, Contract.expires_at > now)


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


async def create(db: AsyncSession, orderer: Character, target_name, kills, price, now: datetime | None = None) -> Contract:
    now = now or _now()
    kills, price = _int(kills), _int(price)
    if kills is None or not cc.MIN_KILLS <= kills <= cc.MAX_KILLS:
        raise ContractError(f"Убийств в заказе - от {cc.MIN_KILLS} до {cc.MAX_KILLS}.")
    if price is None or not cc.MIN_PRICE <= price <= cc.MAX_PRICE:
        raise ContractError(f"За одно убийство - от {cc.MIN_PRICE} самоцветов.")
    name = target_name.strip() if isinstance(target_name, str) else ""
    target = await db.scalar(
        select(Character).where(
            (Character.name == name) | (func.lower(Character.name) == name.lower()),
            Character.creation_state.is_(None),
        ).limit(1)
    ) if name else None
    if target is None:
        raise ContractError("Игрока с таким ником нет.")
    if target.id == orderer.id:
        raise ContractError("Себя заказать нельзя.")
    if target.level < cc.TARGET_MIN_LEVEL:
        raise ContractError(f"Заказать можно игрока с {cc.TARGET_MIN_LEVEL} уровня.")
    total = kills * price
    try:
        await wallet_service.charge(db, orderer.id, "donate", total)
    except wallet_service.NotEnoughCurrency:
        raise ContractError(f"Не хватает самоцветов: заказ стоит 💎{total}.") from None
    contract = Contract(
        orderer_id=orderer.id, target_id=target.id, kills_total=kills, kills_left=kills, price=price,
        status="active", created_at=now, expires_at=now + timedelta(hours=cc.HOURS),
    )
    db.add(contract)
    await db.flush()
    return contract


async def take(db: AsyncSession, hunter: Character, contract_id, now: datetime | None = None) -> Contract:
    now = now or _now()
    cid = _int(contract_id)
    contract = await db.get(Contract, cid) if cid is not None else None
    if contract is None or contract.status != "active" or _aware(contract.expires_at) <= now or contract.kills_left <= 0:
        raise ContractError("Этот заказ уже закрыт.")
    if contract.target_id == hunter.id:
        raise ContractError("Это заказ на тебя.")
    if contract.orderer_id == hunter.id:
        raise ContractError("Свой заказ взять нельзя.")
    if await db.get(ContractTaker, (contract.id, hunter.id)) is not None:
        raise ContractError("Ты уже взял этот заказ.")
    db.add(ContractTaker(contract_id=contract.id, character_id=hunter.id, taken_at=now))
    await db.flush()
    return contract


async def active_contracts(db: AsyncSession, now: datetime | None = None) -> list[Contract]:
    now = now or _now()
    return list((await db.scalars(select(Contract).where(*_active(now)).order_by(Contract.created_at.desc()))).all())


async def taken_ids(db: AsyncSession, hunter_id: int) -> set[int]:
    return set((await db.scalars(select(ContractTaker.contract_id).where(ContractTaker.character_id == hunter_id))).all())


async def taker_counts(db: AsyncSession, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = await db.execute(
        select(ContractTaker.contract_id, func.count()).where(ContractTaker.contract_id.in_(ids))
        .group_by(ContractTaker.contract_id)
    )
    return dict(rows.all())


async def hunted_ids(db: AsyncSession, hunter_id: int, now: datetime | None = None) -> set[int]:
    """Цели, на которых у охотника взят действующий заказ."""
    now = now or _now()
    return set((await db.scalars(
        select(Contract.target_id).join(ContractTaker, ContractTaker.contract_id == Contract.id)
        .where(ContractTaker.character_id == hunter_id, *_active(now))
    )).all())


async def hunts(db: AsyncSession, hunter_id: int, target_id: int, now: datetime | None = None) -> bool:
    return target_id in await hunted_ids(db, hunter_id, now)


async def is_target(db: AsyncSession, character_id: int, now: datetime | None = None) -> bool:
    now = now or _now()
    return await db.scalar(
        select(Contract.id).where(Contract.target_id == character_id, *_active(now)).limit(1)
    ) is not None


@dataclass
class KillPayout:
    """Итог убийства цели по заказам: кому сколько и что сказать."""

    hunter_lines: dict[int, list[str]] = field(default_factory=dict)
    victim_lines: list[str] = field(default_factory=list)
    orderer_notes: list[tuple[int, str]] = field(default_factory=list)   # (character_id, текст)
    finished_for_target: bool = False


async def on_kill(
    db: AsyncSession, victim: Character, killer_ids: list[int], now: datetime | None = None,
) -> KillPayout:
    """Цель убита (killer_ids - кто её бил, первым - кто нанёс больше всех).
    По каждому действующему заказу, который взял кто-то из убийц, - одно
    убийство: цена поровну между взявшими, остаток от деления - первому."""
    now = now or _now()
    out = KillPayout()
    if not killer_ids:
        return out
    contracts = (await db.scalars(
        select(Contract).where(Contract.target_id == victim.id, *_active(now))
        .order_by(Contract.created_at).with_for_update().execution_options(populate_existing=True)
    )).all()
    for contract in contracts:
        takers = set((await db.scalars(
            select(ContractTaker.character_id).where(ContractTaker.contract_id == contract.id)
        )).all())
        paid = [k for k in killer_ids if k in takers]
        if not paid:
            continue
        share, rest = divmod(contract.price, len(paid))
        for i, hunter_id in enumerate(paid):
            amount = share + (rest if i == 0 else 0)
            if amount > 0:
                await wallet_service.deposit(db, hunter_id, "donate", amount)
            split = f" (делёж на {len(paid)})" if len(paid) > 1 else ""
            out.hunter_lines.setdefault(hunter_id, []).append(
                f"📜 Заказ на {victim.name} выполнен: +💎{amount}{split}. Осталось убийств: {contract.kills_left - 1}."
            )
        contract.kills_left -= 1
        if contract.kills_left <= 0:
            contract.status = "done"
        if contract.orderer_id:
            out.orderer_notes.append((
                contract.orderer_id,
                f"📜 Твой заказ на {victim.name}: убийство выполнено, осталось {contract.kills_left} из {contract.kills_total}.",
            ))
        out.victim_lines.append(f"📜 Тебя убили по заказу. Осталось убийств по нему: {contract.kills_left}.")
    await db.flush()
    if out.victim_lines and not await is_target(db, victim.id, now):
        out.finished_for_target = True
        out.victim_lines.append("Заказов на тебя больше нет - мирные клетки и АФК снова защищают.")
    return out


async def expire(db: AsyncSession, now: datetime | None = None) -> list[int]:
    """Истёкшие заказы - сгорают. Возвращает цели, на которых больше нет заказов."""
    now = now or _now()
    rows = (await db.scalars(
        select(Contract).where(Contract.status == "active", Contract.expires_at <= now)
        .with_for_update(skip_locked=True)
    )).all()
    targets = set()
    for contract in rows:
        contract.status = "expired"
        targets.add(contract.target_id)
    await db.flush()
    return [t for t in targets if not await is_target(db, t, now)]


def location_text(target: Character) -> str:
    """Где цель - для /заказ и доски: в городе её не достать."""
    if target.pos_x is None:
        return "неизвестно где"
    city = grid.city_region_at(target.pos_x, target.pos_y)
    if city is not None:
        from bot.onboarding_texts import REGION_TITLES

        return f"в городе ({REGION_TITLES[city]}) - там не тронуть"
    return f"клетка ({target.pos_x}; {target.pos_y})"


def visible_on_map(target: Character) -> bool:
    return target.pos_x is not None and grid.city_region_at(target.pos_x, target.pos_y) is None
