"""Операции с кошельками.

Списание и начисление идут ОДНИМ SQL-выражением (`column - amount` прямо в
UPDATE), а не через чтение в питон и запись обратно. Причина не в красоте:
вебхук запускает каждое событие VK отдельной задачей (`asyncio.create_task`
в bot/webhook.py), то есть два нажатия одной кнопки обрабатываются
ПАРАЛЛЕЛЬНО, каждое в своей сессии. При чтении-изменении-записи оба
обработчика видели баланс 100, оба записывали 40, и игрок получал две
покупки по цене одной. Дедуп по event_id от этого не спасает: у двух
настоящих нажатий разные id.

Проверка «хватает ли» живёт в том же UPDATE (`WHERE column >= amount`).
Postgres сериализует конкурирующие UPDATE одной строки, и второй
обработчик перечитывает условие уже по новому балансу - значит честно
получает NotEnoughCurrency вместо тихого перерасхода.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Wallet


class NotEnoughCurrency(Exception):
    """Недостаточно валюты для операции."""


def _column(currency: str):
    return Wallet.farm_currency if currency == "farm" else Wallet.donate_currency


async def get_wallet(db: AsyncSession, character_id: int) -> Wallet:
    wallet = await db.scalar(select(Wallet).where(Wallet.character_id == character_id))
    if wallet is None:
        wallet = Wallet(character_id=character_id)
        db.add(wallet)
        await db.flush()
    return wallet


async def charge(db: AsyncSession, character_id: int, currency: str, amount: int) -> Wallet:
    """Списывает валюту ('farm' | 'donate'); кидает NotEnoughCurrency."""
    wallet = await get_wallet(db, character_id)  # строка обязана существовать
    column = _column(currency)
    result = await db.execute(
        update(Wallet)
        .where(Wallet.character_id == character_id, column >= amount)
        .values({column: column - amount})
    )
    if not result.rowcount:
        balance = getattr(wallet, "farm_currency" if currency == "farm" else "donate_currency")
        raise NotEnoughCurrency(f"Нужно {amount} ({currency}), есть {balance}")
    # UPDATE прошёл мимо ORM, объект в сессии ещё помнит старое число.
    await db.refresh(wallet)
    return wallet


async def deposit(db: AsyncSession, character_id: int, currency: str, amount: int) -> Wallet:
    wallet = await get_wallet(db, character_id)
    column = _column(currency)
    await db.execute(
        update(Wallet)
        .where(Wallet.character_id == character_id)
        .values({column: column + amount})
    )
    await db.refresh(wallet)
    return wallet
