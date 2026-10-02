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


async def charge(db: AsyncSession, character_id: int, currency: str, amount: int) -> Wallet:
    """Списывает валюту ('farm' | 'donate'); кидает NotEnoughCurrency."""
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
    return wallet


async def deposit(
    db: AsyncSession, character_id: int, currency: str, amount: int, taxable: bool = True,
) -> Wallet:
    """Начисление. Единственная точка, через которую игрок получает золото, -
    поэтому здесь же налог гильдии: его доля уходит в казну, игроку - остаток.
    При передаче между игроками налог платит получатель (сюда приходит его
    начисление). taxable=False - выдачи из самой казны и возврат при роспуске:
    налог с денег гильдии гонял бы их по кругу."""
    wallet = await get_wallet(db, character_id)
    column = _column(currency)
    if currency == "farm" and taxable and amount > 0:
        amount -= await _guild_tax(db, character_id, amount)
    await db.execute(
        update(Wallet)
        .where(Wallet.character_id == character_id)
        .values({column: column + amount})
    )
    await db.refresh(wallet)
    return wallet
