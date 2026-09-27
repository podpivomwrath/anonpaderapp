"""Мощь (гирскор) персонажа - одно число «насколько он силён» (патч 111).

    Мощь = (статы персонажа + статы надетых вещей)
           × (1 + бонус подкласса + бонус за каждый активный микробафф)

Статы персонажа - распределённые (без экипировки); у вещей берётся их
текущая раскладка, поэтому заточка кованого оружия и рост уровня вещей
учтены сами собой. Служебные вещи (Перо Хранителя и т.п.) не считаются: это
инструмент проверки, и в топах они показали бы не силу, а доступ к админке.

Только отображение: в бою Мощь не участвует и ничего не меняет.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, CharacterStats
from services import item_service, preset_service

#: Надбавка за выбранный подкласс (30+ уровень).
SUBCLASS_BONUS = 0.10
#: Надбавка за каждый микробафф активного пресета.
PER_BUFF_BONUS = 0.03


@dataclass
class Power:
    total: int
    stats: int
    gear: int
    subclass_bonus: float
    buffs: int

    @property
    def multiplier(self) -> float:
        return 1.0 + self.subclass_bonus + PER_BUFF_BONUS * self.buffs


def compute(stats_sum: int, gear_sum: int, has_subclass: bool, buffs: int) -> Power:
    subclass_bonus = SUBCLASS_BONUS if has_subclass else 0.0
    base = stats_sum + gear_sum
    total = round(base * (1.0 + subclass_bonus + PER_BUFF_BONUS * buffs))
    return Power(total=total, stats=stats_sum, gear=gear_sum, subclass_bonus=subclass_bonus, buffs=buffs)


async def power_of(db: AsyncSession, character: Character) -> Power:
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    stats_sum = (
        stats.strength + stats.agility + stats.intellect + stats.vitality + stats.will
    ) if stats is not None else 0
    equipped = await item_service.get_equipped(db, character.id)
    gear_sum = sum(
        item_service.item_power(item) for item in equipped.values()
        if item is not None and not item.admin_only
    )
    buffs = 0
    if character.subclass is not None:
        preset = await preset_service.get_active_preset(db, character.id)
        buffs = len(preset.buff_ids) if preset is not None else 0
    return compute(stats_sum, gear_sum, character.subclass is not None, buffs)


async def power_by_id(db: AsyncSession, character_id: int) -> int | None:
    character = await db.get(Character, character_id)
    return (await power_of(db, character)).total if character is not None else None
