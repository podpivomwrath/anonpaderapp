"""Контент из content/*.json проходит Pydantic-валидацию."""

from game.content_loader import BUFF_CATEGORIES, load_content


def test_content_loads_and_validates() -> None:
    content = load_content()
    assert "wolf" in content.mobs
    assert content.mobs["wolf"].level >= 1
    assert "rusty_sword" in content.items
    assert content.items["rusty_sword"].tier == "grey"


def test_guardian_buff_pool_structure() -> None:
    """Пул Стража: категории валидны, есть все 4 категории (п.7)."""
    content = load_content()
    guardian_pool = [b for b in content.buffs.values() if b.subclass == "guardian"]
    assert len(guardian_pool) >= 12  # пул 12-15 баффов
    categories = {b.category for b in guardian_pool}
    assert categories == BUFF_CATEGORIES
    for buff in guardian_pool:
        assert buff.category in BUFF_CATEGORIES
