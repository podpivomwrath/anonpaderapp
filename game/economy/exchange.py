"""Биржа самоцветов. Игра выступает ДИЛЕРОМ (не P2P ордербук).

Принципы:
  - торгуют только лотами по EXCHANGE_BLOCK_SIZE;
  - цена лота растёт и падает в ПРОЦЕНТАХ (сложный процент) от чистого
    объёма, купленного игроками: каждый купленный лот поднимает цену
    следующего на EXCHANGE_LOT_GROWTH, каждый проданный - опускает;
  - продажа лота - на EXCHANGE_SPREAD_PCT дешевле его покупки на шаг ниже,
    поэтому round-trip (купить -> продать) убыточен на любом объёме, а
    сговор нескольких аккаунтов вместе тоже в минусе;
  - у цены есть пол (EXCHANGE_MIN_LOT_PRICE), спред действует и на нём;
  - никаких дневных лимитов: курс выстраивают сами игроки.

Состояние курса (чистый объём) - строка exchange_state
(services/exchange_service.py); история сделок - exchange_orders.
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import ExchangeOrder, OrderDirection
from services.wallet_service import charge, deposit


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
    buy_price: int    # золота за следующий лот при покупке
    sell_price: int   # золота за следующий лот при продаже
    net_sold: int     # чистый объём, проданный игрокам
    block: int


class Exchange:
    """Дилерская биржа с фиксированным спредом и линейным шагом цены."""

    def __init__(self, state: ExchangeStateStore) -> None:
        self._state = state

    # --- Цены ---

    @staticmethod
    def _lot_of(position: int) -> int:
        """Ступень курса: сколько лотов игроки купили сверх проданного (бывает
        и отрицательной - тогда курс ниже стартового)."""
        return position // bc.EXCHANGE_BLOCK_SIZE

    @staticmethod
    def lot_buy_price(level: int) -> int:
        """Цена покупки лота на ступени level. Потолок нужен не для игры (до
        него не дойти никаким золотом), а чтобы степень не переполняла float
        и сумма лотов влезала в BIGINT кошелька."""
        level = max(min(level, 5000), -5000)
        price = bc.EXCHANGE_START_LOT_PRICE * (1 + bc.EXCHANGE_LOT_GROWTH) ** level
        return min(max(round(price), bc.EXCHANGE_MIN_LOT_PRICE), bc.EXCHANGE_MAX_LOT_PRICE)

    @classmethod
    def lot_sell_price(cls, level: int) -> int:
        """Выручка за лот, проданный со ступени level (курс уходит на level-1):
        цена покупки на ступени ниже минус спред. Значит, лот, купленный на
        level-1, продаётся обратно всегда дешевле, чем был куплен."""
        return round(cls.lot_buy_price(level - 1) * (1 - bc.EXCHANGE_SPREAD_PCT))

    @classmethod
    def buy_price_at(cls, position: int) -> int:
        return cls.lot_buy_price(cls._lot_of(position))

    @classmethod
    def sell_price_at(cls, position: int) -> int:
        return cls.lot_sell_price(cls._lot_of(position))

    @classmethod
    def buy_cost(cls, net_sold: int, amount: int) -> int:
        """Стоимость amount самоцветов (кратно лоту): лот за лотом вверх."""
        level = cls._lot_of(net_sold)
        return sum(cls.lot_buy_price(level + i) for i in range(amount // bc.EXCHANGE_BLOCK_SIZE))

    @classmethod
    def sell_gain(cls, net_sold: int, amount: int) -> int:
        """Выручка за amount самоцветов (кратно лоту): лот за лотом вниз."""
        level = cls._lot_of(net_sold)
        return sum(cls.lot_sell_price(level - i) for i in range(amount // bc.EXCHANGE_BLOCK_SIZE))

    async def quote(self) -> ExchangeQuote:
        net_sold = await self._state.get_net_sold()
        return ExchangeQuote(
            buy_price=self.buy_price_at(net_sold),
            sell_price=self.sell_price_at(net_sold),
            net_sold=net_sold,
            block=self._lot_of(net_sold),
        )

    # --- Сделки ---

    async def buy_donate(
        self, db: AsyncSession, character_id: int, amount: int
    ) -> ExchangeOrder:
        """Игрок покупает донат-валюту за золото."""
        if amount <= 0 or amount % bc.EXCHANGE_BLOCK_SIZE:
            raise ValueError("Объём - целые лоты")
        net_sold = await self._state.get_net_sold()
        cost = self.buy_cost(net_sold, amount)

        # Только через атомарные операции кошелька (патч 96). Прямое
        # `wallet.farm_currency -= cost` читало баланс в питон: два
        # одновременных нажатия оба проходили проверку и платили ОДНУ цену,
        # а самоцветы получали дважды. Биржа пока не подключена к игре - это
        # мина на день подключения, а не открытая дыра.
        await charge(db, character_id, "farm", cost)
        await deposit(db, character_id, "donate", amount)
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
        if amount <= 0 or amount % bc.EXCHANGE_BLOCK_SIZE:
            raise ValueError("Объём - целые лоты")
        net_sold = await self._state.get_net_sold()
        gain = self.sell_gain(net_sold, amount)

        await charge(db, character_id, "donate", amount)
        # Биржу налог гильдии не касается (решение владельца): выручка целиком.
        await deposit(db, character_id, "farm", gain, taxable=False)
        await self._state.add_net_sold(-amount)

        order = ExchangeOrder(
            character_id=character_id,
            direction=OrderDirection.SELL,
            amount=amount,
            gold_amount=gain,
        )
        db.add(order)
        return order
