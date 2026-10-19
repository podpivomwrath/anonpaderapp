"""Переделка персонажа у Хранителя Списков: класс, подкласс, характеристики.

Три уровня, как в дизайне (п.8):
  1. переключение между сохранёнными пресетами — бесплатно (preset_service);
  2. изменение состава пресета — за фарм-валюту (preset_service);
  3. смена класса/подкласса и сброс характеристик — этот модуль.

На время альфа-теста третий уровень бесплатен и без ограничений: флаг
bc.ALPHA_FREE_RESPEC. Когда альфа кончится, флаг выключается - и списание
включается обратно само, трогать вызывающий код не придётся.

ВАЖНО про пресеты. Пул баффов у каждого подкласса свой. С 2026-10-19 пресеты
при смене класса и подкласса НЕ удаляются (решение владельца): каждый пресет
принадлежит подклассу своих баффов, и видно и действует только у него
(preset_service.belongs). Вернулся на прежний подкласс - пресеты на месте.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import BaseClass, Character, CharacterStats
from services.wallet_service import charge


async def _reset_stats_rows(db: AsyncSession, character: Character, base_class: str) -> None:
    """Характеристики — к стартовому распределению класса, все набранные за
    уровни очки возвращаются нераспределёнными."""
    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    if stats is None:
        return
    start = bc.STARTING_STATS[base_class]
    stats.strength = start["STR"]
    stats.agility = start["AGI"]
    stats.intellect = start["INT"]
    stats.vitality = start["VIT"]
    stats.will = start["WIL"]
    stats.unspent_points = bc.STAT_POINTS_PER_LEVEL * (character.level - 1)


async def full_class_reset(
    db: AsyncSession, character: Character, new_base_class: BaseClass
) -> Character:
    """Смена базового класса с нуля:
    - списывает CLASS_RESET_COST_DONATE донат-валюты (кроме альфы);
    - сбрасывает подкласс (пресеты остаются - см. докстринг модуля);
    - статы возвращаются к стартовым, очки прокачки — в unspent_points.
    """
    if not bc.ALPHA_FREE_RESPEC:
        await charge(db, character.id, "donate", bc.CLASS_RESET_COST_DONATE)

    character.base_class = new_base_class
    if character.subclass is not None:
        character.subclass_free_repick = True
    character.subclass = None
    await _reset_stats_rows(db, character, new_base_class)
    return character


async def reset_subclass(db: AsyncSession, character: Character) -> Character:
    """Сброс ТОЛЬКО подкласса: базовый класс и характеристики остаются.

    Пресеты остаются - у прежнего подкласса, см. докстринг модуля.
    Прогресс испытаний не трогаем: он привязан к id баффов, и если игрок
    вернётся к прежнему подклассу, открытое останется открытым.
    """
    if not bc.ALPHA_FREE_RESPEC:
        await charge(db, character.id, "donate", bc.SUBCLASS_RESET_COST_DONATE)

    if character.subclass is not None:
        character.subclass_free_repick = True
    character.subclass = None
    return character


async def reset_stats(db: AsyncSession, character: Character) -> Character:
    """Сброс характеристик: класс и подкласс остаются, очки возвращаются.

    Пресеты не трогаем — они от статов не зависят.
    """
    if not bc.ALPHA_FREE_RESPEC:
        await charge(db, character.id, "farm", bc.STATS_RESET_COST_FARM)

    await _reset_stats_rows(db, character, character.base_class)
    return character
