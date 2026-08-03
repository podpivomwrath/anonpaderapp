"""Типы локаций по клетке карты (ux-patch-10, блок 4)."""

from game.content_loader import load_location_types
from game.world import location_types


def test_all_regions_have_four_types() -> None:
    types = load_location_types()
    by_region: dict[str, int] = {}
    for t in types:
        by_region[t.region] = by_region.get(t.region, 0) + 1
    assert by_region == {"ridge": 4, "woods": 4, "docks": 4, "scorched": 4}


def test_region_by_quadrant() -> None:
    assert location_types.region_for(10, 10) == "ridge"
    assert location_types.region_for(-10, 10) == "woods"
    assert location_types.region_for(10, -10) == "docks"
    assert location_types.region_for(-10, -10) == "scorched"
    # граничные случаи (ось) — детерминированный тай-брейк, но не падает
    assert location_types.region_for(0, 0) == "ridge"
    assert location_types.region_for(0, -5) == "docks"
    assert location_types.region_for(-5, 0) == "woods"


def test_same_cell_always_same_type() -> None:
    first = location_types.location_type_at(-49, 49)
    second = location_types.location_type_at(-49, 49)
    assert first.id == second.id


def test_type_matches_cell_region() -> None:
    t = location_types.location_type_at(-30, 40)
    assert t.region == "woods"
    t2 = location_types.location_type_at(30, -40)
    assert t2.region == "docks"


def test_type_has_description_pool() -> None:
    for t in load_location_types():
        assert len(t.descriptions) >= 2


def test_some_types_have_photo_images() -> None:
    """Патч 25: первые 5 типов получили реальные фото; остальные пока без
    картинки — image остаётся None, это ожидаемо, не заглушка."""
    with_image = {t.id for t in load_location_types() if t.image is not None}
    assert with_image == {
        "ridge_terraces", "ridge_redoubt", "ridge_mines", "ridge_pass", "woods_thicket",
    }
