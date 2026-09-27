"""Типы локаций по клетке карты (ux-patch-10, блок 4)."""

from game.content_loader import load_location_types
from game.world import location_types


def test_all_regions_have_four_types() -> None:
    types = load_location_types()
    by_region: dict[str, int] = {}
    for t in types:
        by_region[t.region] = by_region.get(t.region, 0) + 1
    assert by_region == {"ridge": 4, "woods": 4, "docks": 4, "scorched": 4}


def test_region_by_compass_sector() -> None:
    assert location_types.region_for(2, 20) == "ridge"
    assert location_types.region_for(-20, 3) == "woods"
    assert location_types.region_for(20, -3) == "docks"
    assert location_types.region_for(-2, -20) == "scorched"
    # на диагонали клетка уходит к северу/югу; центр - Кряж (тай-брейк)
    assert location_types.region_for(10, 10) == "ridge"
    assert location_types.region_for(-10, -10) == "scorched"
    assert location_types.region_for(0, 0) == "ridge"


def test_same_cell_always_same_type() -> None:
    first = location_types.location_type_at(-25, 5)
    second = location_types.location_type_at(-25, 5)
    assert first.id == second.id


def test_type_matches_cell_region() -> None:
    t = location_types.location_type_at(-25, 5)
    assert t.region == "woods"
    t2 = location_types.location_type_at(25, -5)
    assert t2.region == "docks"


def test_type_has_description_pool() -> None:
    for t in load_location_types():
        assert len(t.descriptions) >= 2


def test_all_types_have_photo_images() -> None:
    """Патч 25: первые 5 типов получили реальные фото; патч 31 («картинки»)
    добавил фото для остальных 11 — теперь все 16 типов локаций с image."""
    types = load_location_types()
    assert all(t.image is not None for t in types)
    assert len(types) == 16
