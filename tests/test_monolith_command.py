"""Команда «Монолит» и подсказка о ней в панели локации.

Кнопка «коснуться Монолита» приходит вместе с клавиатурой движения, то есть
только при ВХОДЕ на клетку. Игроку, который уже стоял на (0; 0), приходилось
уходить и возвращаться, чтобы открыть лобби рейда.
"""

import random

import bot.raid_texts as rt
from bot.world_summary import location_summary
from game.economy import raid_config as rc


class _Character:
    def __init__(self, x: int, y: int) -> None:
        self.pos_x, self.pos_y = x, y
        self.level = 30
        self.experience = 0
        self.raid_keys = 0
        self.region = "ridge"
        self.current_hp = None      # полное здоровье: vitals_service посчитает сам


class _Stats:
    strength = agility = intellect = vitality = will = 20


def _panel(x: int, y: int) -> str:
    return location_summary(_Character(x, y), _Stats(), random.Random(1), farm_currency=0)


def test_hint_is_shown_at_the_monolith() -> None:
    assert rt.MONOLITH_HINT_LINE in _panel(*rc.MONOLITH_COORDS)


def test_hint_is_not_shown_elsewhere() -> None:
    assert rt.MONOLITH_HINT_LINE not in _panel(3, 4)


def test_hint_names_the_actual_command() -> None:
    """Подсказка обязана называть ту же команду, которую ловит обработчик -
    иначе текст разойдётся с игрой при первом же переименовании."""
    import bot.handlers.raid as raid_handlers

    assert rt.MONOLITH_COMMAND in rt.MONOLITH_HINT_LINE
    patterns = [
        pattern.text
        for handler in raid_handlers.labeler.message_view.handlers
        for rule in handler.rules
        for pattern in getattr(rule, "patterns", ())
    ]
    assert rt.MONOLITH_COMMAND in patterns


def test_command_and_button_share_one_path() -> None:
    """Команда и кнопка ведут в один и тот же обработчик: проверки занятости и
    позиции не должны разъехаться между двумя входами."""
    import inspect

    import bot.handlers.raid as raid_handlers

    body = inspect.getsource(raid_handlers._open_raid_list)
    assert "blocked_reason" in body
    assert "chebyshev_distance" in body
