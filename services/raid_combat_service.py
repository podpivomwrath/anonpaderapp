"""Рейд «Кукольный театр» (патч 53): награды этапов — множители к опыту/
броскам трофеев (×2/×3/×5, см. game/economy/raid_config.py) + гарантированный
предмет не ниже заданной редкости одному случайному участнику.

Резолв самого боя — game/combat/tick_engine.py (та же машина, is_raid=True),
оркестрация (когда открывать окно прерывания Хирурга, порядок Вельдов,
переход между этапами) — bot/handlers/raid_combat.py. Здесь — только
PvE-специфичная логика наград вокруг него (тот же принцип, что и
services/group_combat_service.py)."""

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy import item_config as ic
from game.economy import item_gen
from models import Character, CharacterStats, Inventory, Item
from services import (
    experience_service,
    group_service,
    item_service,
    raid_key_service,
    trophy_service,
)

_RARITY_FLOOR_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]


@dataclass
class MobKillReward:
    character_id: int
    xp_gained: int
    xp_premium_applied: bool
    levels_gained: int
    new_level: int
    trophies: dict[str, int] = field(default_factory=dict)
    items_dropped: list[Item] = field(default_factory=list)
    raid_key_dropped: bool = False
    group_kick: "group_service.LevelGapKick | None" = None


async def reward_mob_kill(
    db: AsyncSession, alive_members: list[Character], mob_level: int, rng: random.Random, loot_mult: int,
) -> list[MobKillReward]:
    """Как group_combat_service.reward_mob_kill, но опыт умножен на
    loot_mult, а трофеи/предметы/ключ — loot_mult НЕЗАВИСИМЫХ бросков
    каждому (текст патча: "×N к КОЛИЧЕСТВУ БРОСКОВ трофеев", не к шансу)."""
    if not alive_members:
        return []
    total_levels = sum(m.level for m in alive_members)
    base_total = experience_service.xp_per_mob(mob_level) * loot_mult
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

        # Патч 58: ровно +1 за моба, ВНЕ цикла loot_mult — множитель
        # умножает добычу, а не число убитых.
        character.mobs_killed += 1
        trophies_total: dict[str, int] = {}
        items_dropped: list[Item] = []
        raid_key_dropped = False
        for _ in range(loot_mult):
            trophies = await trophy_service.grant_from_kill(db, character, rng)
            for trophy_id, count in trophies.items():
                trophies_total[trophy_id] = trophies_total.get(trophy_id, 0) + count
            item = await item_service.grant_from_kill(db, character, mob_level, rng)
            if item is not None:
                items_dropped.append(item)
            if await raid_key_service.maybe_grant(db, character, rng):
                raid_key_dropped = True

        rewards.append(
            MobKillReward(
                character_id=character.id, xp_gained=levelup.xp_awarded,
                xp_premium_applied=levelup.premium_applied,
                levels_gained=levelup.levels_gained, new_level=levelup.new_level,
                trophies=trophies_total, items_dropped=items_dropped,
                raid_key_dropped=raid_key_dropped, group_kick=group_kick,
            )
        )
    return rewards


def _roll_rarity_at_least(rng: random.Random, floor_rarity: str) -> str:
    floor_idx = _RARITY_FLOOR_ORDER.index(floor_rarity)
    allowed = _RARITY_FLOOR_ORDER[floor_idx:]
    weights = [ic.ITEM_RARITY_CHANCES[r] for r in allowed]
    return rng.choices(allowed, weights=weights, k=1)[0]


async def grant_guaranteed_item(
    db: AsyncSession, character: Character, ilvl: int, rng: random.Random, floor_rarity: str,
) -> Item:
    """Гарантированный предмет НЕ НИЖЕ floor_rarity — текст патча:
    "Гарантирован 1 предмет снаряжения не ниже 🔵/🟣/🟠 — одному случайному
    участнику" за этапы 1/2/3 соответственно."""
    rarity_id = _roll_rarity_at_least(rng, floor_rarity)
    slot = item_gen.roll_slot(rng)
    primary_stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    generated = item_gen.generate_item(
        rng, ilvl=ilvl, slot=slot, rarity_id=rarity_id,
        primary_stat=primary_stat, bases=item_service.bases(), rarities=item_service.rarities(),
    )
    item = Item(
        name=generated.name, slot=generated.slot, base_stats=generated.base_stats,
        rarity=generated.rarity, ilvl=generated.ilvl,
    )
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=False))
    await db.flush()
    return item
