"""Предупреждение о глубине рудника (патч 98).

Штраф за глубину - намеренный барьер, но его не было видно: новичок у
глубокой жилы узнавал о нём, только начав копать, а о том, что руда всё равно
будет по его уровню, - не узнавал вовсе.
"""

from bot import mining_texts as mt
from game import content_loader as cl
from game.economy import mining_config as mc


def _mine(tier: int):
    return next(m for m in cl.load_mines() if m.tier == tier)


def test_no_warning_when_the_mine_fits_the_level() -> None:
    for tier, need in mc.MINE_REQUIRED_LEVEL.items():
        assert mt.depth_warning(_mine(tier), need) is None


def test_newbie_at_the_deepest_mine_is_warned_about_time_and_ore() -> None:
    text = mt.depth_warning(_mine(5), 1)
    assert text is not None
    assert str(mc.MINE_REQUIRED_LEVEL[5]) in text
    assert "ч" in text, "у самой глубокой жилы новичок копает больше часа - это и надо сказать"
    assert "Руда глубже" in text


def test_warning_is_a_single_line() -> None:
    """Вход в рудник видят часто: повторяющееся - одной строкой."""
    assert "\n" not in mt.depth_warning(_mine(5), 1)
