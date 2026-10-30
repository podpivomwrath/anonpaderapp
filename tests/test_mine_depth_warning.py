"""Строка времени при входе в рудник (патч 98; с 2026-10-30 - всегда).

Штраф за глубину - намеренный барьер, но его не было видно: новичок у
глубокой жилы узнавал о нём, только начав копать, а о том, что руда всё равно
будет по его уровню, - не узнавал вовсе. Владелец (2026-10-30): время куска
писать при каждом входе, а не только у рудника не по уровню.
"""

from bot import mining_texts as mt
from game import content_loader as cl
from game.economy import mining_config as mc


def _mine(tier: int):
    return next(m for m in cl.load_mines() if m.tier == tier)


def test_time_is_shown_even_when_the_mine_fits_the_level() -> None:
    for tier, need in mc.MINE_REQUIRED_LEVEL.items():
        text = mt.dig_time_line(_mine(tier), need)
        assert text.startswith("⏳ Кусок займёт от 5 мин до 15 мин"), text
        assert "Не по уровню" not in text


def test_pick_and_guild_speed_shorten_the_range() -> None:
    assert mt.dig_time_line(_mine(1), 1, speed=0.5) == "⏳ Кусок займёт от 2 мин до 8 мин."


def test_newbie_at_the_deepest_mine_is_warned_about_time_and_ore() -> None:
    text = mt.dig_time_line(_mine(5), 1)
    assert str(mc.MINE_REQUIRED_LEVEL[5]) in text
    assert "ч" in text, "у самой глубокой жилы новичок копает больше часа - это и надо сказать"
    assert "Руда глубже" in text


def test_line_is_single() -> None:
    """Вход в рудник видят часто: повторяющееся - одной строкой."""
    assert "\n" not in mt.dig_time_line(_mine(5), 1)
