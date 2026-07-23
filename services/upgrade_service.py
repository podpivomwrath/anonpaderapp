"""Заточка и пробуждение экипировки (п.9 дизайна).

- Заточка до +20: неудача откатывает на 1 шаг (материалы расходуются всегда;
  учёт материалов — TODO: content);
- Пробуждение на +20: 30% шанс полностью уничтожить предмет (с частичным
  возвратом ресурсов на новый крафт), успех открывает слот под самоцвет.
- Принципиально БЕЗ доната — только игровые ресурсы.
"""

import random
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import Item, ItemUpgradeHistory


class UpgradeError(Exception):
    pass


@dataclass
class UpgradeResult:
    success: bool
    item_destroyed: bool = False
    level_before: int = 0
    level_after: int = 0
    refund_ratio: float = 0.0  # доля ресурсов к возврату при уничтожении


async def enchant(db: AsyncSession, item: Item, rng: random.Random) -> UpgradeResult:
    """Попытка заточки: +1 при успехе, откат на 1 шаг при неудаче."""
    if item.enchant_level >= bc.ENCHANT_MAX_LEVEL:
        raise UpgradeError(f"Предмет уже на +{bc.ENCHANT_MAX_LEVEL} — доступно пробуждение")
    before = item.enchant_level
    success = rng.random() < bc.ENCHANT_SUCCESS_CHANCE
    item.enchant_level = before + 1 if success else max(before - 1, 0)

    db.add(
        ItemUpgradeHistory(
            item_id=item.id,
            action="enchant",
            success=success,
            level_before=before,
            level_after=item.enchant_level,
        )
    )
    return UpgradeResult(
        success=success, level_before=before, level_after=item.enchant_level
    )


async def awaken(db: AsyncSession, item: Item, rng: random.Random) -> UpgradeResult:
    """Пробуждение на +20: 30% — предмет уничтожен (частичный возврат ресурсов),
    успех — открыт слот под самоцвет (socketed_gem_id)."""
    if item.enchant_level < bc.ENCHANT_MAX_LEVEL:
        raise UpgradeError(f"Пробуждение доступно только на +{bc.ENCHANT_MAX_LEVEL}")
    if item.awakened:
        raise UpgradeError("Предмет уже пробуждён")

    destroyed = rng.random() < bc.AWAKENING_DESTRUCTION_CHANCE
    db.add(
        ItemUpgradeHistory(
            item_id=item.id,
            action="awaken",
            success=not destroyed,
            level_before=item.enchant_level,
            level_after=item.enchant_level,
            item_destroyed=destroyed,
        )
    )
    if destroyed:
        await db.flush()  # история должна попасть в БД до удаления предмета
        await db.delete(item)
        return UpgradeResult(
            success=False,
            item_destroyed=True,
            level_before=bc.ENCHANT_MAX_LEVEL,
            level_after=0,
            refund_ratio=bc.AWAKENING_REFUND_RATIO,
        )
    item.awakened = True  # слот самоцвета открыт (самоцвет — отдельный предмет)
    return UpgradeResult(
        success=True,
        level_before=bc.ENCHANT_MAX_LEVEL,
        level_after=bc.ENCHANT_MAX_LEVEL,
    )
