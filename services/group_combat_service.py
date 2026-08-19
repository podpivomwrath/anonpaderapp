"""Групповой PvE-бой (патч 51, ч.4): состав противников (мобов столько же,
сколько участников; уровень — по МАКСИМАЛЬНОМУ уровню в группе, как если бы
бой начал самый высокоуровневый участник — обычная clamp-формула по зоне уже
внутри game/world/encounters.py::spawn_mob, дополнительной логики не нужно),
деление опыта пропорционально уровню среди живых на момент гибели моба
(защита от паровозов), независимый бросок лута каждому. Резолв самого боя —
существующий game/combat/tick_engine.py (та же машина, что и групповой PvP,
патч 38); здесь только PvE-специфичная логика вокруг него."""

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, CharacterStats
from services import (
    experience_service,
    group_service,
    item_service,
    raid_key_service,
    trophy_service,
)
from game.world import encounters


def spawn_mobs(
    members: list[Character], region: str, dist: int, rng: random.Random, start_id: int,
) -> list[encounters.Encounter]:
    """Мобов столько же, сколько участников (1 к 1); уровень каждого — по
    максимальному уровню в группе."""
    max_level = max(m.level for m in members)
    return [
        encounters.spawn_mob(start_id + i, region, max_level, dist, rng)
        for i in range(len(members))
    ]


@dataclass
class MobKillReward:
    character_id: int
    xp_gained: int
    xp_premium_applied: bool
    levels_gained: int
    new_level: int
    trophies: dict[str, int] = field(default_factory=dict)
    item_dropped: object = None
    raid_key_dropped: bool = False
    group_kick: "group_service.LevelGapKick | None" = None


async def reward_mob_kill(
    db: AsyncSession, alive_members: list[Character], mob_level: int, rng: random.Random,
) -> list[MobKillReward]:
    """Опыт за ОДНОГО убитого моба делится пропорционально уровню между
    живыми на момент его гибели участниками:

        доля_игрока = уровень_игрока / сумма_уровней_живых_участников
        опыт_игрока = общий_опыт_за_моба * доля_игрока

    К доле каждого затем применяется обычный множитель за разницу уровней
    (патч 26, experience_service.mob_xp_level_diff_multiplier) — низкоуровневый
    всё равно получает бонус за то, что моб выше него. Выбывшие (погибшие до
    гибели этого моба) не в alive_members — не участвуют в делении и не
    получают лут с него (см. bot/handlers/group_combat.py)."""
    if not alive_members:
        return []
    total_levels = sum(m.level for m in alive_members)
    base_total = experience_service.xp_per_mob(mob_level)
    rewards: list[MobKillReward] = []
    for character in alive_members:
        share = base_total * (character.level / total_levels)
        mult = experience_service.mob_xp_level_diff_multiplier(mob_level, character.level)
        xp_amount = round(share * mult)
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        levelup = experience_service.add_experience(character, stats, xp_amount)
        group_kick = None
        if levelup.levels_gained > 0:
            group_kick = await group_service.enforce_level_gap(db, character)
        trophies = await trophy_service.grant_from_kill(db, character, rng)
        item = await item_service.grant_from_kill(db, character, mob_level, rng)
        raid_key_dropped = await raid_key_service.maybe_grant(db, character, rng)
        rewards.append(
            MobKillReward(
                character_id=character.id, xp_gained=levelup.xp_awarded,
                xp_premium_applied=levelup.premium_applied,
                levels_gained=levelup.levels_gained, new_level=levelup.new_level,
                trophies=trophies, item_dropped=item, raid_key_dropped=raid_key_dropped,
                group_kick=group_kick,
            )
        )
    return rewards
