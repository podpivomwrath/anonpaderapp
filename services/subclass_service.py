"""Выбор подкласса на 30 уровне за золото (патч 12, «Раскол пути»).

Одноразово: после character.subclass выбран, эта сцена больше не доступна
(полный ресет класса — отдельная будущая задача, см. respec_service.py).
"""

from game.classes.base import REGISTRY, SubclassDef
from game.combat import balance_config as bc
from models import Character
from services.wallet_service import charge


#: Пул баффов базового класса у отказавшихся от подкласса (2026-10-20):
#: в content/buffs.json у таких баффов "subclass": "<класс>_path".
PATH_SUFFIX = "_path"


def can_offer(character: Character) -> bool:
    return (
        character.level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL
        and character.subclass is None
        and not declined(character)
    )


def declined(character) -> bool:
    return bool(getattr(character, "subclass_declined", False))


def path_chosen(character) -> bool:
    """Путь на 30 уровне решён: выбран подкласс или от него отказались.
    Для сюжета это одно и то же."""
    return character.subclass is not None or declined(character)


def buff_pool(character) -> str | None:
    """Чьи баффы собирает игрок в пресеты: подкласса или базового класса
    (отказ от подкласса). None - пока путь не решён."""
    if character.subclass is not None:
        return character.subclass
    if declined(character) and character.base_class:
        return f"{character.base_class}{PATH_SUFFIX}"
    return None


def is_path_pool(pool: str | None) -> bool:
    """Пул базового класса: открыт сразу, без испытаний."""
    return bool(pool) and pool.endswith(PATH_SUFFIX)


def decline(character: Character) -> None:
    """Отказ от подкласса - бесплатно и навсегда (снимает только смена класса)."""
    character.subclass_declined = True
    # 2026-10-21, владелец: отказ - такой же выбор пути, как подкласс. Значит,
    # и право на бесплатный повторный выбор после сброса - как у подкласса.
    character.subclass_free_repick = True


def paths_for(base_class: str) -> list[SubclassDef]:
    """Два подкласса, доступных базовому классу персонажа (порядок REGISTRY)."""
    return [s for s in REGISTRY.values() if s.base_class == base_class]


def free_repick(character: Character) -> bool:
    """Путь выбирается заново после смены класса/подкласса - без платы, пока
    действует «Дар первопроходцев»."""
    from game.economy import prerelease_config

    return prerelease_config.free_path_repick() and bool(getattr(character, "subclass_free_repick", False))


async def pay_unlock(db, character: Character) -> int:
    """Списывает SUBCLASS_UNLOCK_COST золота; кидает NotEnoughCurrency, если не хватает.
    После смены класса/подкласса - бесплатно. Возвращает списанное."""
    if free_repick(character):
        return 0
    await charge(db, character.id, "farm", bc.SUBCLASS_UNLOCK_COST)
    return bc.SUBCLASS_UNLOCK_COST


def apply_subclass(character: Character, subclass_id: str) -> None:
    """Записывает подкласс — вызывать ПОСЛЕ pay_unlock и подтверждения игрока."""
    character.subclass = subclass_id
    # 2026-10-21 (репорт Archon): флаг - «за путь уже платили», он больше не
    # сгорает. Раньше выбор его гасил, а отказ от пути стирал: подкласс ->
    # сброс -> отказ -> смена класса, и Хранитель снова просил 20 000.
    character.subclass_free_repick = True
