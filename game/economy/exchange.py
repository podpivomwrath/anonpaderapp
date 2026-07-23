"""Биржа фарм↔донат валюты. Игра выступает ДИЛЕРОМ (не P2P ордербук).

Принципы (п.10 дизайна):
  - цена покупки доната растёт ступенчато и ЛИНЕЙНО за каждый блок в
    EXCHANGE_BLOCK_SIZE донат-валюты (по чистому объёму, проданному игрокам);
  - спред фиксирован: sell = buy - EXCHANGE_SPREAD, поэтому round-trip
    (купить → продать) математически убыточен;
  - никаких дневных лимитов: рынок саморегулируется двумя типами участников
    (фармилы и донатеры двигают чистый объём в разные стороны);
  - донат не влияет на исход операций — только игровая валюта и время.

Live-состояние (чистый проданный объём) — в Redis; история сделок — в
exchange_orders (Postgres).
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import ExchangeOrder, OrderDirection
from services.wallet_service import NotEnoughCurrency, get_wallet


class ExchangeStateStore(Protocol):
    """Хранилище чистого объёма донат-валюты, проданного игрокам."""

    async def get_net_sold(self) -> int: ...

    async def add_net_sold(self, delta: int) -> int:
        """Атомарно сдвигает объём, возвращает новое значение."""
        ...


class InMemoryExchangeState:
    def __init__(self, net_sold: int = 0) -> None:
        self._net_sold = net_sold

    async def get_net_sold(self) -> int:
        return self._net_sold

    async def add_net_sold(self, delta: int) -> int:
        self._net_sold += delta
        return self._net_sold


class RedisExchangeState:
    KEY = "exchange:net_donate_sold"

    def __init__(self, redis) -> None:  # redis.asyncio.Redis
        self._redis = redis

    async def get_net_sold(self) -> int:
        value = await self._redis.get(self.KEY)
        return int(value) if value is not None else 0

    async def add_net_sold(self, delta: int) -> int:
        return int(await self._redis.incrby(self.KEY, delta))


@dataclass
class ExchangeQuote:
    buy_price: int    # золота за 1 донат при покупке (текущий блок)
    sell_price: int   # золота за 1 донат при продаже (текущий блок)
    net_sold: int     # чистый объём, проданный игрокам
    block: int


class Exchange:
    """Дилерская биржа с фиксированным спредом и линейным шагом цены."""

    def __init__(self, state: ExchangeStateStore) -> None:
        self._state = state

    # --- Цены ---

    @staticmethod
    def _block_of(position: int) -> int:
        # объём может уйти в минус (донатеры продали больше, чем куплено) —
        # цена ниже базовой не опускается
        return max(position // bc.EXCHANGE_BLOCK_SIZE, 0)

    @classmethod
    def buy_price_at(cls, position: int) -> int:
        return bc.EXCHANGE_BASE_BUY_PRICE + bc.EXCHANGE_PRICE_STEP * cls._block_of(position)

    @classmethod
    def sell_price_at(cls, position: int) -> int:
        return max(cls.buy_price_at(position) - bc.EXCHANGE_SPREAD, bc.EXCHANGE_MIN_SELL_PRICE)

    @classmethod
    def buy_cost(cls, net_sold: int, amount: int) -> int:
        """Стоимость покупки amount доната: ступенчато по блокам вверх.

        При position < 0 цена базовая (блок 0), поэтому граница первого
        «настоящего» блока (BLOCK_SIZE) корректна и для отрицательной зоны.
        """
        total, position, remaining = 0, net_sold, amount
        while remaining > 0:
            block_end = (cls._block_of(position) + 1) * bc.EXCHANGE_BLOCK_SIZE
            take = min(remaining, block_end - position)
            total += take * cls.buy_price_at(position)
            position += take
            remaining -= take
        return total

    @classmethod
    def sell_gain(cls, net_sold: int, amount: int) -> int:
        """Выручка за продажу amount доната: ступенчато по блокам вниз."""
        total, position, remaining = 0, net_sold, amount
        while remaining > 0:
            if position <= 0:
                # ниже нулевой отметки цена не опускается
                total += remaining * cls.sell_price_at(0)
                break
            block_start = cls._block_of(position - 1) * bc.EXCHANGE_BLOCK_SIZE
            take = min(remaining, position - block_start)
            total += take * cls.sell_price_at(position - 1)
            position -= take
            remaining -= take
        return total

    async def quote(self) -> ExchangeQuote:
        net_sold = await self._state.get_net_sold()
        return ExchangeQuote(
            buy_price=self.buy_price_at(net_sold),
            sell_price=self.sell_price_at(net_sold - 1 if net_sold > 0 else 0),
            net_sold=net_sold,
            block=self._block_of(net_sold),
        )

    # --- Сделки ---

    async def buy_donate(
        self, db: AsyncSession, character_id: int, amount: int
    ) -> ExchangeOrder:
        """Игрок покупает донат-валюту за золото."""
        if amount <= 0:
            raise ValueError("Объём должен быть положительным")
        net_sold = await self._state.get_net_sold()
        cost = self.buy_cost(net_sold, amount)

        wallet = await get_wallet(db, character_id)
        if wallet.farm_currency < cost:
            raise NotEnoughCurrency(f"Нужно {cost} золота, есть {wallet.farm_currency}")
        wallet.farm_currency -= cost
        wallet.donate_currency += amount
        await self._state.add_net_sold(amount)

        order = ExchangeOrder(
            character_id=character_id,
            direction=OrderDirection.BUY,
            amount=amount,
            gold_amount=cost,
        )
        db.add(order)
        return order

    async def sell_donate(
        self, db: AsyncSession, character_id: int, amount: int
    ) -> ExchangeOrder:
        """Игрок продаёт донат-валюту за золото."""
        if amount <= 0:
            raise ValueError("Объём должен быть положительным")
        wallet = await get_wallet(db, character_id)
        if wallet.donate_currency < amount:
            raise NotEnoughCurrency(
                f"Нужно {amount} донат-валюты, есть {wallet.donate_currency}"
            )
        net_sold = await self._state.get_net_sold()
        gain = self.sell_gain(net_sold, amount)

        wallet.donate_currency -= amount
        wallet.farm_currency += gain
        await self._state.add_net_sold(-amount)

        order = ExchangeOrder(
            character_id=character_id,
            direction=OrderDirection.SELL,
            amount=amount,
            gold_amount=gain,
        )
        db.add(order)
        return order
