"""«Осмотреться» на мирной клетке отвечает, а не молчит (жалоба игрока)."""

from bot.handlers import pvp


def test_peaceful_scene_alone() -> None:
    text = pvp._peaceful_scene_text([])
    assert "Ты один" in text and "мирное" in text


async def test_peaceful_scene_lists_players_without_numbers(make_character) -> None:
    other = await make_character(level=12)
    text = pvp._peaceful_scene_text([other])
    assert other.name in text and "1." not in text and "мирное" in text


def test_city_gates_are_pvp_free() -> None:
    """Город и 2 клетки вокруг него во все стороны - без PvP (2026-10-15:
    было 1); на шаг дальше - обычная клетка."""
    from game.world import grid

    assert grid.pvp_forbidden(0, 30)                # Кряж
    assert grid.pvp_forbidden(1, 29) and grid.pvp_forbidden(-1, 30) and grid.pvp_forbidden(0, 29)
    assert grid.pvp_forbidden(0, 28) and grid.pvp_forbidden(2, 29) and grid.pvp_forbidden(-2, 28)
    assert grid.at_city_gates(28, 0) and not grid.at_city_gates(30, 0)
    assert not grid.pvp_forbidden(0, 27) and not grid.pvp_forbidden(3, 29)
    assert not grid.pvp_forbidden(10, 10)
