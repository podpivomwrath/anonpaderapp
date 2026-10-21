"""Травничество (2026-10-21): рост на случайных клетках, сбор, уровень."""

import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from bot.handlers import herbs as herb_handlers
from game.economy import herbal_config as hc
from game.economy import herbalism
from game.world import grid
from models import HerbPatch
from services import herb_service

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class _Always(random.Random):
    """random() всегда 0 - любой шанс срабатывает."""

    def random(self):
        return 0.0


async def _plant(db, x, y, herb_id="bitter_wormwood", at=NOW):
    patch = HerbPatch(x=x, y=y, herb_id=herb_id, spawned_at=at)
    db.add(patch)
    await db.flush()
    return patch


def test_catalog_two_herbs_per_tier_and_no_yo() -> None:
    tiers = Counter(h.tier for h in herbalism.herb_defs_ordered())
    assert tiers == {1: 2, 2: 2, 3: 2, 4: 2, 5: 2}
    # Владелец: в ремеслах без «ё».
    assert not any("ё" in (h.name + h.description).lower() for h in herbalism.herb_defs_ordered())


def test_ring_tier_is_favoured_but_not_exclusive() -> None:
    rng = random.Random(1)
    x, y = 0, 29  # внешнее кольцо
    tiers = Counter(herbalism.roll_herb(rng, x, y).tier for _ in range(4000))
    ring = grid.ring_tier(x, y)
    assert tiers[ring] > 1500 and all(tiers[t] > 200 for t in hc.TIER_LEVEL)


def test_xp_curve_and_cap() -> None:
    assert herbalism.xp_to_next(1) == 41 and herbalism.xp_to_next(hc.MAX_LEVEL) == 0
    # 2026-10-21, «ещё медленнее»: до 50-го ~19 000 опыта (было 5 390).
    total = sum(herbalism.xp_to_next(level) for level in range(1, hc.MAX_LEVEL))
    assert 17000 < total < 21000
    assert herbalism.double_chance(9) == 0 and herbalism.double_chance(50) == 0.5


async def test_spawn_goes_to_random_cell_not_explorers(db_session, monkeypatch) -> None:
    monkeypatch.setattr(hc, "SPAWN_CHANCE", 1.0)
    rng = random.Random(5)
    cells = set()
    for _ in range(40):
        patch = await herb_service.spawn(db_session, rng, (3, 3), NOW)
        assert patch is not None
        cells.add((patch.x, patch.y))
        assert grid.in_bounds(patch.x, patch.y) and grid.city_region_at(patch.x, patch.y) is None
    assert (3, 3) not in cells and len(cells) == 40


async def test_spawn_respects_chance_and_cap(db_session, monkeypatch) -> None:
    class _Never(random.Random):
        def random(self):
            return 0.99

    assert await herb_service.spawn(db_session, _Never(1), (0, 0), NOW) is None
    monkeypatch.setattr(hc, "MAP_CAP", 2)
    monkeypatch.setattr(hc, "SPAWN_CHANCE", 1.0)
    rng = random.Random(2)
    assert await herb_service.spawn(db_session, rng, (0, 0), NOW) is not None
    assert await herb_service.spawn(db_session, rng, (0, 0), NOW) is not None
    assert await herb_service.spawn(db_session, rng, (0, 0), NOW) is None
    # Завявшие сметаются: через сутки место снова есть.
    assert await herb_service.spawn(db_session, rng, (0, 0), NOW + timedelta(hours=25)) is not None


async def test_pick_gives_bag_and_xp_and_removes_patch(db_session, character_at) -> None:
    c = await character_at(5, 20)
    patch = await _plant(db_session, 5, 20)
    found = await herb_service.visible_here(db_session, c, NOW)
    assert found is not None and found[1].id == "bitter_wormwood"
    res = await herb_service.pick(db_session, c, patch.id, random.Random(1), NOW)
    assert res.status == "ok" and res.amount == 1 and res.xp == 10
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, c.id)] == [("bitter_wormwood", 1)]
    assert (await herb_service.pick(db_session, c, patch.id, random.Random(1), NOW)).status == "gone"
    assert "пучок в сумке" in herb_handlers.picked_text(res)
    # Шкала опыта ремесла под логом (2026-10-21).
    assert "🌿 Травничество 1 ур.: ▰▰▱▱▱▱▱▱▱▱ 10 / 41" in herb_handlers.picked_text(res, c)


async def test_pick_refuses_elsewhere_unseen_and_withered(db_session, character_at) -> None:
    c = await character_at(5, 20)
    far = await _plant(db_session, 6, 20)
    assert (await herb_service.pick(db_session, c, far.id, random.Random(1), NOW)).status == "elsewhere"
    deep = await _plant(db_session, 5, 20, herb_id="stone_bloom")
    assert await herb_service.visible_here(db_session, c, NOW) is None
    assert (await herb_service.pick(db_session, c, deep.id, random.Random(1), NOW)).status == "unseen"
    await db_session.delete(deep)
    await db_session.flush()
    old = await _plant(db_session, 5, 20, at=NOW - timedelta(hours=25))
    assert (await herb_service.pick(db_session, c, old.id, random.Random(1), NOW)).status == "gone"


async def test_level_up_unlocks_next_tier_and_double(db_session, character_at) -> None:
    c = await character_at(5, 20)
    c.herbalism_level, c.herbalism_xp = 9, herbalism.xp_to_next(9) - 5
    patch = await _plant(db_session, 5, 20)
    res = await herb_service.pick(db_session, c, patch.id, _Always(1), NOW)
    assert res.level_after == 10 and [h.tier for h in res.unlocked] == [2, 2]
    assert res.amount == 1  # на 9 уровне шанса двойного ещё нет
    patch = await _plant(db_session, 5, 20)
    assert (await herb_service.pick(db_session, c, patch.id, _Always(1), NOW)).amount == 2
    text = herb_handlers.picked_text(res)
    assert "10 уровень" in text and "Солончаковая лебеда" in text


def test_cap_stops_xp() -> None:
    class C:
        herbalism_level = hc.MAX_LEVEL
        herbalism_xp = 0

    c = C()
    herb_service.grant_xp(c, 500)
    assert (c.herbalism_level, c.herbalism_xp) == (hc.MAX_LEVEL, 0)
