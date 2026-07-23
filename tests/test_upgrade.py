"""Заточка до +20 и пробуждение (п.9)."""

import random

import pytest
from sqlalchemy import select

from game.combat import balance_config as bc
from models import Item, ItemUpgradeHistory
from services.upgrade_service import UpgradeError, awaken, enchant


class FixedRng(random.Random):
    def __init__(self, value: float) -> None:
        super().__init__()
        self._value = value

    def random(self) -> float:
        return self._value


async def make_item(db_session, enchant_level: int = 0, awakened: bool = False) -> Item:
    item = Item(name="Меч", slot="weapon", tier="blue", enchant_level=enchant_level, awakened=awakened)
    db_session.add(item)
    await db_session.flush()
    return item


async def test_enchant_success(db_session) -> None:
    item = await make_item(db_session, 5)
    result = await enchant(db_session, item, FixedRng(0.0))  # < шанс успеха
    assert result.success and item.enchant_level == 6


async def test_enchant_failure_rolls_back_one_step(db_session) -> None:
    item = await make_item(db_session, 5)
    result = await enchant(db_session, item, FixedRng(0.99))
    assert not result.success and item.enchant_level == 4  # откат на шаг


async def test_enchant_failure_at_zero_stays_zero(db_session) -> None:
    item = await make_item(db_session, 0)
    await enchant(db_session, item, FixedRng(0.99))
    assert item.enchant_level == 0


async def test_enchant_capped_at_max(db_session) -> None:
    item = await make_item(db_session, bc.ENCHANT_MAX_LEVEL)
    with pytest.raises(UpgradeError):
        await enchant(db_session, item, FixedRng(0.0))


async def test_awaken_requires_max_enchant(db_session) -> None:
    item = await make_item(db_session, 19)
    with pytest.raises(UpgradeError):
        await awaken(db_session, item, FixedRng(0.9))


async def test_awaken_success_opens_socket(db_session) -> None:
    item = await make_item(db_session, bc.ENCHANT_MAX_LEVEL)
    result = await awaken(db_session, item, FixedRng(0.9))  # > 30% — выжил
    assert result.success and item.awakened


async def test_awaken_destroys_item_with_partial_refund(db_session) -> None:
    item = await make_item(db_session, bc.ENCHANT_MAX_LEVEL)
    item_id = item.id
    result = await awaken(db_session, item, FixedRng(0.1))  # < 30% — уничтожен
    await db_session.flush()

    assert result.item_destroyed
    assert result.refund_ratio == bc.AWAKENING_REFUND_RATIO
    assert await db_session.get(Item, item_id) is None
    # история попытки сохранилась несмотря на уничтожение предмета
    history = (
        await db_session.scalars(
            select(ItemUpgradeHistory).where(ItemUpgradeHistory.action == "awaken")
        )
    ).all()
    assert len(history) == 1 and history[0].item_destroyed


async def test_double_awaken_rejected(db_session) -> None:
    item = await make_item(db_session, bc.ENCHANT_MAX_LEVEL, awakened=True)
    with pytest.raises(UpgradeError):
        await awaken(db_session, item, FixedRng(0.9))
