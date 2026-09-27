"""Патч 109: объём текстов - описания локаций, базы вещей, системные реплики."""

from game.content_loader import load_location_types, load_story_line
from game.economy import item_gen
from game.world import flavor, grid
from game.world.location_types import location_type_at, region_for
from models import Item
from services import item_service, naming


def test_every_location_type_has_six_descriptions() -> None:
    for t in load_location_types():
        assert len(t.descriptions) >= 6, t.id
        assert len(set(t.descriptions)) == len(t.descriptions), t.id


def test_every_generated_name_resolves_to_its_own_base() -> None:
    """Иконка ищется по подстроке базы в имени - новые базы не должны
    перехватывать чужие имена ни при какой редкости."""
    for slot, bases in item_service.bases().items():
        assert len(bases) >= 6, slot
        for base in bases:
            for rarity in ("common", "uncommon", "rare", "epic", "legendary"):
                name = item_gen.build_name(base, item_service.rarity_def(rarity))
                key = naming.item_icon_key(Item(name=name, slot=slot, base_stats={}))
                assert key == f"base:{slot}:{base.name}", name


def test_death_text_is_stable_within_one_death() -> None:
    assert len({flavor.death_line(12345) for _ in range(20)}) == 1


def test_state_pools_have_variety() -> None:
    assert len({flavor.death_line(seed) for seed in range(200)}) >= 4
    assert len({flavor.rest_start() for _ in range(200)}) >= 3
    assert len({flavor.rest_done() for _ in range(200)}) >= 3


def test_respawn_line_keeps_city_name_intact() -> None:
    for _ in range(50):
        assert flavor.respawn_line("🏰 Обетованный Кряж").startswith("🏰 Обетованный Кряж.")


def test_woods_act_three_is_in_the_second_ring_like_other_regions() -> None:
    for region in ("ridge", "docks", "scorched", "woods"):
        act3 = next(a for a in load_story_line(region).acts if a.act == 3)
        target = next(q for q in act3.quests if q.target_x is not None)
        assert grid.ring_tier(target.target_x, target.target_y) == 2, region
        assert region_for(target.target_x, target.target_y) == region
    woods3 = next(a for a in load_story_line("woods").acts if a.act == 3)
    q = next(q for q in woods3.quests if q.target_x is not None)
    assert location_type_at(q.target_x, q.target_y).name == q.target_label
