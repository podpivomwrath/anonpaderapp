"""Групповой PvE-бой (патч 51, ч.4): состав мобов, деление опыта, лут."""

import random

from services import group_combat_service as gcs
from services import experience_service


def _char(id_, level):
    class C:
        pass

    c = C()
    c.id = id_
    c.level = level
    return c


def test_spawn_mobs_count_matches_members() -> None:
    members = [_char(1, 10), _char(2, 12), _char(3, 8)]
    mobs = gcs.spawn_mobs(members, "ridge", dist=45, rng=random.Random(1), start_id=100)
    assert len(mobs) == 3


def test_spawn_mobs_level_by_max_party_level() -> None:
    members = [_char(1, 5), _char(2, 40)]
    mobs = gcs.spawn_mobs(members, "ridge", dist=45, rng=random.Random(1), start_id=100)
    # Уровень моба клампится в диапазон зоны — на dist=45 (последнее кольцо)
    # верхняя граница заведомо ниже 40, поэтому мобы должны быть заметно
    # выше, чем если бы уровень брался по минимальному участнику (5).
    assert all(m.combatant.level > 5 for m in mobs)


def test_spawn_mobs_ids_are_sequential_from_start() -> None:
    members = [_char(1, 10), _char(2, 10)]
    mobs = gcs.spawn_mobs(members, "ridge", dist=45, rng=random.Random(1), start_id=50)
    assert [m.combatant.id for m in mobs] == [50, 51]


async def test_reward_mob_kill_splits_xp_proportionally_to_level(db_session, character_at) -> None:
    low = await character_at(5, 5, level=10)
    high = await character_at(5, 5, level=30)
    rewards = await gcs.reward_mob_kill(db_session, [low, high], mob_level=20, rng=random.Random(1))
    by_id = {r.character_id: r for r in rewards}
    # Высокоуровневый должен получить БОЛЬШЕ опыта, чем низкоуровневый —
    # доля пропорциональна уровню (30 против 10).
    assert by_id[high.id].xp_gained > by_id[low.id].xp_gained


async def test_reward_mob_kill_applies_level_diff_bonus_on_top_of_share(db_session, character_at) -> None:
    solo = await character_at(5, 5, level=5)
    # Один "живой" участник — вся база опыта достаётся ему (доля = 1.0),
    # но множитель за разницу уровней (моб намного выше) должен применяться.
    reward = (await gcs.reward_mob_kill(db_session, [solo], mob_level=50, rng=random.Random(1)))[0]
    base = experience_service.xp_per_mob(50)
    mult = experience_service.mob_xp_level_diff_multiplier(50, 5)
    assert reward.xp_gained == round(base * mult)


async def test_reward_mob_kill_grants_independent_loot_per_player(db_session, make_character) -> None:
    a = await character_pos(make_character, 5, 5, level=10)
    b = await character_pos(make_character, 5, 5, level=10)
    rewards = await gcs.reward_mob_kill(db_session, [a, b], mob_level=10, rng=random.Random(7))
    assert len(rewards) == 2
    # Каждому — свой независимый результат (не обязаны совпадать, но оба присутствуют)
    ids = {r.character_id for r in rewards}
    assert ids == {a.id, b.id}


async def test_reward_mob_kill_empty_alive_list_returns_empty(db_session) -> None:
    assert await gcs.reward_mob_kill(db_session, [], mob_level=10, rng=random.Random(1)) == []


async def character_pos(make_character, x, y, **kwargs):
    character = await make_character(**kwargs)
    character.pos_x = x
    character.pos_y = y
    return character
