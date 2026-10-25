"""«Осмотреться» на мирной клетке отвечает, а не молчит (жалоба игрока)."""

from bot.handlers import pvp


def test_peaceful_scene_alone() -> None:
    text = pvp._peaceful_scene_text([])
    assert "Ты один" in text and "мирное" in text


async def test_peaceful_scene_lists_players_without_numbers(make_character) -> None:
    other = await make_character(level=12)
    text = pvp._peaceful_scene_text([other])
    assert other.name in text and "1." not in text and "мирное" in text


def test_peaceful_scene_shows_contract_fight() -> None:
    """Бой по заказу на озере видят все на клетке (2026-10-25)."""
    battle = pvp.Battle(battle_type="duel", location=(5, 5))
    for cid, name, side in ((1, "Охотник", 0), (2, "Цель", 1)):
        battle.participants[cid] = pvp.Participant(cid, cid, name, "warrior", "Воин")
        battle.side_of[cid] = side
    text = pvp._peaceful_scene_text([], None, [(7, battle)])
    assert "Ты один" not in text and "Охотник vs Цель" in text and "по заказу" in text


async def test_attack_drops_fishing_and_closes_lake(db_session, make_character) -> None:
    from datetime import datetime, timezone

    victim = await make_character(level=20)
    victim.screen = "lake"
    victim.fishing_cast_at = datetime.now(timezone.utc)
    text = await pvp._drop_craft_work(db_session, victim)
    assert text and victim.fishing_cast_at is None and victim.screen is None


async def test_attack_leaves_plain_cell_alone(db_session, make_character) -> None:
    victim = await make_character(level=20)
    assert await pvp._drop_craft_work(db_session, victim) is None


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
    assert grid.pvp_forbidden(0, 0)  # Монолит (2026-10-22)
