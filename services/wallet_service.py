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

import sys

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Wallet, WalletLog

#: Сколько последних операций хранить на персонажа (2026-10-21, владелец: 20).
WALLET_LOG_KEEP = 20


def _caller(depth: int = 2) -> str:
    """«модуль.функция», откуда пришло списание или начисление: причину не
    надо передавать из 58 мест вызова, она видна по стеку."""
    frame = sys._getframe(depth)
    module = frame.f_globals.get("__name__", "?").rsplit(".", 1)[-1]
    return f"{module}.{frame.f_code.co_name}"[:64]


async def log_change(
    db: AsyncSession, character_id: int, currency: str, delta: int, balance: int, reason: str,
    note: str | None = None,
) -> None:
    """Записать операцию в журнал и оставить только последние WALLET_LOG_KEEP."""
    if not delta:
        return
    db.add(WalletLog(character_id=character_id, currency=currency, delta=delta, balance=balance,
                     reason=reason[:64], note=note[:64] if note else None))
    await db.flush()
    old = select(WalletLog.id).where(WalletLog.character_id == character_id, WalletLog.id.not_in(
        select(WalletLog.id).where(WalletLog.character_id == character_id)
        .order_by(WalletLog.id.desc()).limit(WALLET_LOG_KEEP)
    ))
    await db.execute(delete(WalletLog).where(WalletLog.id.in_(old)).execution_options(synchronize_session=False))


async def _guild_tax(db: AsyncSession, character_id: int, amount: int) -> int:
    """Сколько золота уходит в казну гильдии с этого начисления."""
    from models import Character, Guild

    row = (
        await db.execute(
            select(Guild.id, Guild.gold_tax).join(Character, Character.guild_id == Guild.id)
            .where(Character.id == character_id)
        )
    ).first()
    if row is None or not row.gold_tax:
        return 0
    cut = amount * row.gold_tax // 100
    if cut > 0:
        await db.execute(
            update(Guild).where(Guild.id == row.id).values(
                treasury_gold=Guild.treasury_gold + cut, tax_collected=Guild.tax_collected + cut,
            ).execution_options(synchronize_session="fetch")
        )
    return cut


async def _lock_taxing_guild(db: AsyncSession, character_id: int) -> None:
    """Порядок блокировок: гильдия раньше кошелька. Начисление с налогом
    сначала обновляет гильдию, потом кошелёк. Списание шло наоборот - кошелёк,
    а налог на последующем начислении (продажа на бирже, ставка в кости,
    перевод) трогал гильдию уже потом. Два таких параллельных события одного
    игрока ловили взаимную блокировку, и Postgres обрывал одно из них.
    Поэтому списание с члена гильдии с налогом сперва берёт строку гильдии.
    Режим - FOR NO KEY UPDATE, как у самого UPDATE налога: обычный FOR UPDATE
    конфликтует со ссылками на гильдию (вставка гильдейского дейлика при
    смене дня) и сам рождал взаимные блокировки - стресс-тест биржи это ловил."""
    from models import Character, Guild

    await db.execute(
        select(Guild.id).join(Character, Character.guild_id == Guild.id)
        .where(Character.id == character_id, Guild.gold_tax > 0)
        .with_for_update(of=Guild, key_share=True)
    )


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


async def charge(
    db: AsyncSession, character_id: int, currency: str, amount: int, reason: str | None = None,
) -> Wallet:
    """Списывает валюту ('farm' | 'donate'); кидает NotEnoughCurrency.
    reason - для журнала; по умолчанию - кто вызвал."""
    reason = reason or _caller()
    wallet = await get_wallet(db, character_id)  # строка обязана существовать
    await _lock_taxing_guild(db, character_id)
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
    await log_change(db, character_id, currency, -amount,
                     wallet.farm_currency if currency == "farm" else wallet.donate_currency, reason)
    return wallet


async def deposit(
    db: AsyncSession, character_id: int, currency: str, amount: int, taxable: bool = True,
    reason: str | None = None,
) -> Wallet:
    """Начисление. Единственная точка, через которую игрок получает золото, -
    поэтому здесь же налог гильдии: его доля уходит в казну, игроку - остаток.
    При передаче между игроками налог платит получатель (сюда приходит его
    начисление). taxable=False - выдачи из самой казны и возврат при роспуске:
    налог с денег гильдии гонял бы их по кругу."""
    reason = reason or _caller()
    wallet = await get_wallet(db, character_id)
    column = _column(currency)
    tax = 0
    if currency == "farm" and taxable and amount > 0:
        tax = await _guild_tax(db, character_id, amount)
        amount -= tax
    await db.execute(
        update(Wallet)
        .where(Wallet.character_id == character_id)
        .values({column: column + amount})
    )
    await db.refresh(wallet)
    await log_change(db, character_id, currency, amount,
                     wallet.farm_currency if currency == "farm" else wallet.donate_currency, reason,
                     note=f"налог гильдии {tax}" if tax else None)
    return wallet
