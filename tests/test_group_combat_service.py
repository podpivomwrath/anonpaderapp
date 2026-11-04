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


def test_spawn_mobs_level_by_cell_not_party() -> None:
    """2026-10-15: уровень мобов группы - от клетки, состав группы не влияет."""
    from game.world import world_config as wc

    members = [_char(1, 5), _char(2, 40)]
    mobs = gcs.spawn_mobs(members, "ridge", dist=20, rng=random.Random(1), start_id=100)
    lo, hi = wc.cell_level_range(20)
    assert all(lo <= m.combatant.level <= hi for m in mobs)


def test_spawn_mobs_ids_are_sequential_from_start() -> None:
    members = [_char(1, 10), _char(2, 10)]
    mobs = gcs.spawn_mobs(members, "ridge", dist=45, rng=random.Random(1), start_id=50)
    assert [m.combatant.id for m in mobs] == [50, 51]


async def test_reward_mob_kill_splits_xp_proportionally_to_level(db_session, character_at) -> None:
    low = await character_at(5, 5, level=10)
    high = await character_at(5, 5, level=30)
    rewards = await gcs.reward_mob_kill(db_session, [low, high], mob_level=20, rng=random.Random(1))
    by_id = {r.character_id: r for r in rewards}
    # Доля пропорциональна уровню (30 против 10), но для 30-го моб 20-го -
    # слабая цель (x0.2), а для 10-го - опасная (x2), 2026-10-15.
    base = experience_service.xp_per_mob(20)
    for who, share in ((low, 10 / 40), (high, 30 / 40)):
        mult = experience_service.mob_xp_level_diff_multiplier(20, who.level)
        assert abs(by_id[who.id].xp_gained - base * share * mult) <= 1


async def test_reward_mob_kill_applies_level_diff_bonus_on_top_of_share(db_session, character_at) -> None:
    solo = await character_at(5, 5, level=5)
    # Один "живой" участник — вся база опыта достаётся ему (доля = 1.0),
    # но множитель за разницу уровней (моб намного выше) должен применяться.
    reward = (await gcs.reward_mob_kill(db_session, [solo], mob_level=50, rng=random.Random(1)))[0]
    base = experience_service.xp_per_mob(50)
    mult = experience_service.mob_xp_level_diff_multiplier(50, 5)
    assert reward.xp_gained == round(base * mult)


async def test_group_loot_chance_falls_with_each_kill(db_session, make_character, monkeypatch) -> None:
    """2026-11-04, владелец: каждый бросает добычу сам; за 1-го моба боя -
    всегда, за 2-го - с шансом 50%, за 3-го - 12,5%, дальше ничего. Опыт - всем."""
    from services import trophy_service

    assert [gcs.loot_share(n) for n in (1, 2, 3, 4, 5)] == [1.0, 0.5, 0.125, 0.0, 0.0]
    rolled = []

    async def fake_trophies(db, character, rng):
        rolled.append(character.id)
        return {}

    monkeypatch.setattr(trophy_service, "grant_from_kill", fake_trophies)
    group = [await character_pos(make_character, 5, 5, level=10) for _ in range(3)]
    rewards = await gcs.reward_mob_kill(db_session, group, mob_level=10, rng=random.Random(1), loot_chance=1.0)
    assert sorted(rolled) == sorted(c.id for c in group)  # первый моб - бросок каждому
    rolled.clear()
    rewards = await gcs.reward_mob_kill(db_session, group, mob_level=10, rng=random.Random(1), loot_chance=0.0)
    assert rolled == [] and all(r.xp_gained > 0 for r in rewards)  # без добычи, но с опытом
    # 50% на 2-го моба: на многих бросках - около половины.
    rng = random.Random(7)
    for _ in range(100):
        await gcs.reward_mob_kill(db_session, group[:1], mob_level=10, rng=rng, loot_chance=0.5)
    assert 30 <= len(rolled) <= 70


async def test_reward_mob_kill_empty_alive_list_returns_empty(db_session) -> None:
    assert await gcs.reward_mob_kill(db_session, [], mob_level=10, rng=random.Random(1)) == []


async def character_pos(make_character, x, y, **kwargs):
    character = await make_character(**kwargs)
    character.pos_x = x
    character.pos_y = y
    return character


def test_group_kills_share() -> None:
    """2026-10-13: убийства в группе - мобы на игроков, округлено, минимум 1."""
    from services.group_combat_service import group_kills_share

    assert group_kills_share(3, 4) == 1   # 0,75 -> 1
    assert group_kills_share(1, 5) == 1   # меньше 1 не бывает
    assert group_kills_share(6, 2) == 3
    assert group_kills_share(5, 2) == 3   # 2,5 -> 3
    assert group_kills_share(0, 3) == 0
