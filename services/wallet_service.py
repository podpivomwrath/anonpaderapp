"""Операции с кошельками."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Wallet


class NotEnoughCurrency(Exception):
    """Недостаточно валюты для операции."""


async def get_wallet(db: AsyncSession, character_id: int) -> Wallet:
    wallet = await db.scalar(select(Wallet).where(Wallet.character_id == character_id))
    if wallet is None:
        wallet = Wallet(character_id=character_id)
        db.add(wallet)
        await db.flush()
    return wallet


async def charge(db: AsyncSession, character_id: int, currency: str, amount: int) -> Wallet:
    """Списывает валюту ('farm' | 'donate'); кидает NotEnoughCurrency."""
    wallet = await get_wallet(db, character_id)
    field = "farm_currency" if currency == "farm" else "donate_currency"
    balance = getattr(wallet, field)
    if balance < amount:
        raise NotEnoughCurrency(f"Нужно {amount} ({currency}), есть {balance}")
    setattr(wallet, field, balance - amount)
    return wallet


async def deposit(db: AsyncSession, character_id: int, currency: str, amount: int) -> Wallet:
    wallet = await get_wallet(db, character_id)
    field = "farm_currency" if currency == "farm" else "donate_currency"
    setattr(wallet, field, getattr(wallet, field) + amount)
    return wallet
