"""Полный ресет класса — третий уровень респека (п.8 дизайна).

Платно донат-валютой (которую можно получить и через биржу за фарм).
"""

from game.combat import balance_config as bc
from models import BaseClass, Character
from services.wallet_service import charge
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CharacterBuffPreset, CharacterStats


async def full_class_reset(
    db: AsyncSession, character: Character, new_base_class: BaseClass
) -> Character:
    """Смена базового класса с нуля:
    - списывает CLASS_RESET_COST_DONATE донат-валюты;
    - сбрасывает подкласс и пресеты баффов (пул баффов другой);
    - статы возвращаются к стартовым, очки прокачки — в unspent_points.
    """
    await charge(db, character.id, "donate", bc.CLASS_RESET_COST_DONATE)

    character.base_class = new_base_class
    character.subclass = None

    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    if stats is not None:
        # Статы — к стартовому распределению НОВОГО класса (онбординг-дизайн)
        start = bc.STARTING_STATS[new_base_class]
        stats.strength = start["STR"]
        stats.agility = start["AGI"]
        stats.intellect = start["INT"]
        stats.vitality = start["VIT"]
        stats.will = start["WIL"]
        stats.unspent_points = bc.STAT_POINTS_PER_LEVEL * (character.level - 1)

    await db.execute(
        delete(CharacterBuffPreset).where(
            CharacterBuffPreset.character_id == character.id
        )
    )
    return character
