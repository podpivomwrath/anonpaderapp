"""Выбор подкласса на 30 уровне за золото (патч 12, «Раскол пути»).

Одноразово: после character.subclass выбран, эта сцена больше не доступна
(полный ресет класса — отдельная будущая задача, см. respec_service.py).
"""

from game.classes.base import REGISTRY, SubclassDef
from game.combat import balance_config as bc
from models import Character
from services.wallet_service import charge


def can_offer(character: Character) -> bool:
    return character.level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL and character.subclass is None


def paths_for(base_class: str) -> list[SubclassDef]:
    """Два подкласса, доступных базовому классу персонажа (порядок REGISTRY)."""
    return [s for s in REGISTRY.values() if s.base_class == base_class]


async def pay_unlock(db, character: Character) -> None:
    """Списывает SUBCLASS_UNLOCK_COST золота; кидает NotEnoughCurrency, если не хватает."""
    await charge(db, character.id, "farm", bc.SUBCLASS_UNLOCK_COST)


def apply_subclass(character: Character, subclass_id: str) -> None:
    """Записывает подкласс — вызывать ПОСЛЕ pay_unlock и подтверждения игрока."""
    character.subclass = subclass_id
