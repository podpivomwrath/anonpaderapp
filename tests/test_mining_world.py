"""Горное дело в мире (патч 59): подсказка, кнопка, ивент жилы, клавиатуры."""

import json
import random

import pytest

from bot import craft_button_state as st
from bot import mining_texts as mt
from bot.keyboards import mining as kb
from game.economy import mining
from game.world import events as event_pool

MINE_XY = (46, 44)
PLAIN_XY = (45, 45)


class _Character:
    def __init__(self, x: int, y: int) -> None:
        self.pos_x, self.pos_y = x, y
        self.level = 30
        self.experience = 0
        self.raid_keys = 0
        self.region = "ridge"
        self.current_hp = None


class _Stats:
    strength = agility = intellect = vitality = will = 20


def _summary(x: int, y: int, ore: int | None = None) -> str:
    from bot.world_summary import location_summary

    return location_summary(
        _Character(x, y), _Stats(), random.Random(0), farm_currency=0, mine_ore_left=ore
    )


def test_mine_hint_is_shown_at_a_mine() -> None:
    text = _summary(*MINE_XY, ore=3)
    assert mt.MINE_HINT_LINE in text
    assert mining.mine_at(*MINE_XY).name in text
    assert "руды 3" in text


def test_summary_does_not_claim_empty_when_it_did_not_look() -> None:
    """mine_ore_left=None значит «вызывающий не ходил в БД», а не «пусто».
    Сводка синхронная и запрос сделать не может — врать ей нельзя."""
    text = _summary(*MINE_XY, ore=None)
    assert mt.MINE_HINT_LINE in text
    assert "жила пуста" not in text
    assert "жила пуста" in _summary(*MINE_XY, ore=0)


def test_mine_hint_is_not_shown_on_a_plain_cell() -> None:
    assert mt.MINE_HINT_LINE not in _summary(*PLAIN_XY)


def test_hint_names_the_command_the_handler_catches() -> None:
    import bot.handlers.mining as mining_handlers

    assert mt.MINE_COMMAND in mt.MINE_HINT_LINE
    assert mining_handlers.mt.MINE_COMMAND == mt.MINE_COMMAND


# --- Кнопка: один раз на вход, отдельно от озёрной ----------------------------

def test_mine_and_lake_buttons_do_not_overwrite_each_other() -> None:
    """У ремёсел свои отметки: иначе отметка рудника гасила бы озёрную."""
    peer = 555001
    st.leave(peer, st.MINE)
    st.leave(peer, st.LAKE)

    st.mark_sent(peer, st.MINE, *MINE_XY)
    assert st.should_send(peer, st.MINE, *MINE_XY) is False
    assert st.should_send(peer, st.LAKE, 41, -41) is True


def test_mine_button_returns_after_leaving_the_cell() -> None:
    peer = 555002
    st.leave(peer, st.MINE)
    st.mark_sent(peer, st.MINE, *MINE_XY)
    assert st.should_send(peer, st.MINE, *MINE_XY) is False
    st.leave(peer, st.MINE)
    assert st.should_send(peer, st.MINE, *MINE_XY) is True


# --- Ивент мелкой жилы --------------------------------------------------------

def test_ore_vein_event_exists_and_has_no_choices() -> None:
    event = event_pool.event_by_id("ore_vein")
    assert event is not None
    assert event.ore_vein is True
    assert not event.choices, "добыча — процесс на минуты, а не мгновенный исход"
    assert event.title and event.text


def test_ore_vein_event_is_in_the_pool() -> None:
    rng = random.Random(9)
    ids = {event_pool.random_event(rng).id for _ in range(500)}
    assert "ore_vein" in ids


# --- Клавиатуры ---------------------------------------------------------------

VK_MAX_ROWS = 10
VK_MAX_PER_ROW = 5


def _rows(raw: str) -> list[list[dict]]:
    return json.loads(raw)["buttons"]


@pytest.mark.parametrize(
    "name, raw",
    [
        ("рудник с рудой", kb.mine_keyboard(True)),
        ("рудник пустой", kb.mine_keyboard(False)),
        ("идёт добыча", kb.digging_keyboard()),
        ("инвентарь руды", kb.ore_keyboard()),
        ("кнопка входа", kb.approach_mine_keyboard()),
        ("кнопка жилы", kb.event_vein_keyboard("ore_vein")),
    ],
)
def test_keyboards_fit_vk_limits(name: str, raw: str) -> None:
    rows = _rows(raw)
    assert len(rows) <= VK_MAX_ROWS, f"{name}: {len(rows)} рядов"
    for row in rows:
        assert len(row) <= VK_MAX_PER_ROW, f"{name}: ряд из {len(row)} кнопок"


def test_empty_mine_hides_the_dig_button() -> None:
    """Предлагать действие, которое гарантированно откажет, хуже, чем не
    предлагать вовсе."""
    empty = [b["action"]["label"] for row in _rows(kb.mine_keyboard(False)) for b in row]
    full = [b["action"]["label"] for row in _rows(kb.mine_keyboard(True)) for b in row]
    assert mt.BTN_DIG not in empty
    assert mt.BTN_DIG in full


def test_mine_screens_always_have_a_way_out() -> None:
    """У каждого экрана рудника есть выход. У забоя он свой — отмена копания:
    выйти наверх, не бросив кирку, нельзя, добыча блокирует всё."""
    for raw in (kb.mine_keyboard(True), kb.mine_keyboard(False), kb.ore_keyboard()):
        labels = [b["action"]["label"] for row in _rows(raw) for b in row]
        assert mt.BTN_LEAVE_MINE in labels
    digging = [b["action"]["label"] for row in _rows(kb.digging_keyboard()) for b in row]
    assert mt.BTN_ABANDON in digging


def test_entry_buttons_are_inline() -> None:
    """Приходят отдельным сообщением и не должны сносить нижнюю клавиатуру."""
    assert json.loads(kb.approach_mine_keyboard())["inline"] is True
    assert json.loads(kb.event_vein_keyboard("ore_vein"))["inline"] is True
