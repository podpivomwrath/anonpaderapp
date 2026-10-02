"""«Осмотреться» на мирной клетке отвечает, а не молчит (жалоба игрока)."""

from bot.handlers import pvp


def test_peaceful_scene_alone() -> None:
    text = pvp._peaceful_scene_text([])
    assert "Ты один" in text and "мирное" in text


async def test_peaceful_scene_lists_players_without_numbers(make_character) -> None:
    other = await make_character(level=12)
    text = pvp._peaceful_scene_text([other])
    assert other.name in text and "1." not in text and "мирное" in text
