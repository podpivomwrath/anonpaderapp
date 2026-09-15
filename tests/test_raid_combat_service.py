"""Патч 53: множители наград рейда — services/raid_combat_service.py."""

import random

from services import experience_service, raid_combat_service as rcs


class FixedRng(random.Random):
    def __init__(self, value: float) -> None:
        self._value = value

    def random(self) -> float:
        return self._value

    def choice(self, seq):
        return seq[0]

    def choices(self, population, weights=None, k=1):
        return [population[0]] * k


async def test_reward_xp_multiplied_by_loot_mult(db_session, character_at) -> None:
    solo = await character_at(0, 0, level=10)
    rng = FixedRng(0.999)  # промах на всех вероятностных бросках трофеев/предметов/ключа

    base_rewards = await rcs.reward_mob_kill(db_session, [solo], mob_level=10, rng=rng, loot_mult=1)
    solo2 = await character_at(0, 0, level=10)
    x2_rewards = await rcs.reward_mob_kill(db_session, [solo2], mob_level=10, rng=rng, loot_mult=2)

    assert x2_rewards[0].xp_gained == base_rewards[0].xp_gained * 2


async def test_reward_loot_rolls_independent_per_mult(db_session, character_at) -> None:
    """rng всегда 'успех' — loot_mult=3 должен дать РОВНО 3 независимых
    попытки трофея/предмета/ключа (не один бросок с утроенным шансом)."""
    character = await character_at(0, 0, level=10)
    rng = FixedRng(0.0)  # гарантированный успех на любой вероятностной проверке

    rewards = await rcs.reward_mob_kill(db_session, [character], mob_level=10, rng=rng, loot_mult=3)
    reward = rewards[0]
    assert len(reward.items_dropped) == 3  # предмет падает каждый из 3 бросков
    assert reward.raid_key_dropped is True


async def test_grant_guaranteed_item_respects_rarity_floor(db_session, make_character) -> None:
    character = await make_character(level=60, base_class="warrior")
    rng = FixedRng(0.0)  # всегда выбирает первый (низший допустимый) вариант в choices
    item = await rcs.grant_guaranteed_item(db_session, character, ilvl=60, rng=rng, floor_rarity="rare")
    assert item.rarity == "rare"  # низший допустимый >= floor, а не common/uncommon

    item_epic_floor = await rcs.grant_guaranteed_item(
        db_session, character, ilvl=60, rng=rng, floor_rarity="epic",
    )
    assert item_epic_floor.rarity == "epic"
