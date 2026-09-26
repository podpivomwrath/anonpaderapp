"""Рыбалка в мире (патч 58): подсказка у воды, ивент рыбака, лимиты клавиатур.

Эти три вещи ломаются тихо:
  - подсказка про «Озеро» — единственная вторая дверь к воде (кнопка приходит
    только при ВХОДЕ на клетку), и если она пропадёт, игрок, уже стоящий у
    озера, просто не найдёт вход;
  - ивент рыбака с пустым садком превратился бы в пустой исход события;
  - клавиатура сверх лимитов VK ломает экран целиком, а не одну кнопку.
"""

import json
import random

import pytest

from bot import fishing_texts as ft
from bot.keyboards import appraiser as akb
from bot.keyboards import fishing as fkb
from bot.keyboards import world as wkb
from game.economy import fishing
from game.economy import fishing_config as fc
from game.world import events as event_pool

# Клетка с озером первого кольца (Отмель Мары) и обычная клетка того же кольца.
LAKE_XY = (41, -41)
PLAIN_XY = (45, 45)


# --- Подсказка у воды ---------------------------------------------------------

class _Character:
    """Минимальный персонаж для сводки локации — как в tests/test_monolith_command.py."""

    def __init__(self, x: int, y: int) -> None:
        self.pos_x, self.pos_y = x, y
        self.level = 30
        self.experience = 0
        self.raid_keys = 0
        self.region = "docks"
        self.current_hp = None


class _Stats:
    strength = agility = intellect = vitality = will = 20


def _summary(x: int, y: int) -> str:
    from bot.world_summary import location_summary

    return location_summary(_Character(x, y), _Stats(), random.Random(0), farm_currency=0)


def test_lake_hint_is_shown_at_a_lake() -> None:
    text = _summary(*LAKE_XY)
    assert ft.LAKE_HINT_LINE in text
    assert fishing.lake_at(*LAKE_XY).name in text


def test_lake_hint_is_not_shown_on_a_plain_cell() -> None:
    assert ft.LAKE_HINT_LINE not in _summary(*PLAIN_XY)


def test_hint_names_the_command_the_handler_actually_catches() -> None:
    """Текст обязан называть ту же команду, которую ловит обработчик — иначе
    подсказка разойдётся с игрой при первом же переименовании."""
    import bot.handlers.fishing as fishing_handlers

    assert ft.LAKE_COMMAND in ft.LAKE_HINT_LINE
    assert fishing_handlers.ft.LAKE_COMMAND == ft.LAKE_COMMAND


def test_plain_cell_is_not_a_lake() -> None:
    assert fishing.is_lake(*PLAIN_XY) is False


# --- Ивент рыбака -------------------------------------------------------------

def test_fisher_event_appears_regardless_of_the_bag() -> None:
    """Рыбак выпадает при любом улове, в том числе пустом.

    Порог «килограмм в садке» был ловушкой: на стартовых озёрах рыба мелкая
    (слепой пескарь — 100-700 г), и новичок не встречал рыбака вообще никогда,
    сколько бы ни исследовал.
    """
    rng = random.Random(3)
    ids = {event_pool.random_event(rng).id for _ in range(500)}
    assert "lakeside_fisher" in ids


def test_fisher_event_has_a_line_for_an_empty_bag() -> None:
    """С пустым садком сцена обязана что-то сказать: «ничего не произошло» —
    запрещённый исход события (правило патча 10)."""
    event = event_pool.event_by_id("lakeside_fisher")
    assert event.fish_trade is True
    assert event.empty_text.strip()
    # В этой ветке выбора нет, поэтому плейсхолдеров цены быть не должно.
    assert "{gold}" not in event.empty_text
    assert "{weight}" not in event.empty_text


def test_all_events_are_equally_likely() -> None:
    """Фильтров в пуле не осталось — если появится новый, шансы всех событий
    поедут, и это должно быть осознанным решением, а не побочным эффектом."""
    rng = random.Random(11)
    counts = {}
    for _ in range(20000):
        eid = event_pool.random_event(rng).id
        counts[eid] = counts.get(eid, 0) + 1
    assert len(counts) == len(event_pool.all_events())
    expected = 20000 / len(counts)
    for eid, n in counts.items():
        assert abs(n - expected) < expected * 0.15, f"{eid}: {n} вместо ~{expected:.0f}"


def test_fisher_event_text_has_both_placeholders() -> None:
    """Шаблон подставляется в bot/handlers/world.py — если плейсхолдер уедет,
    игрок увидит либо KeyError, либо цену без числа."""
    event = event_pool.event_by_id("lakeside_fisher")
    assert "{gold}" in event.text and "{weight}" in event.text
    formatted = event.text.format(gold=123, weight="4,5 кг")
    assert "123" in formatted and "4,5 кг" in formatted


def test_fisher_event_has_a_sell_and_a_refuse_choice() -> None:
    event = event_pool.event_by_id("lakeside_fisher")
    flags = [
        any(outcome.fish_buyer for outcome in choice.outcomes)
        for choice in event.choices
    ]
    assert flags.count(True) == 1, "ровно один выбор должен продавать улов"
    assert flags.count(False) >= 1, "должен остаться выбор отказаться"


def test_deeper_rings_pay_strictly_more() -> None:
    """Весь смысл ивента — тащить улов туда, где опаснее. Если наценки колец
    перестанут расти, смысл пропадёт, а механика останется."""
    previous = (0.0, 0.0)
    for tier in sorted(fc.BUYER_EVENT_MARKUP):
        low, high = fc.BUYER_EVENT_MARKUP[tier]
        assert low < high
        assert low >= previous[0] and high > previous[1], f"тир {tier} не дороже предыдущего"
        previous = (low, high)


def test_event_buyer_always_beats_the_appraiser() -> None:
    """Иргал — гарантированный ПОЛ цены; рыбак обязан быть выше него всегда,
    иначе тащить рыбу вглубь незачем."""
    worst_buyer = min(low for low, _high in fc.BUYER_EVENT_MARKUP.values())
    assert worst_buyer > fc.APPRAISER_FISH_MULTIPLIER


# --- Лимиты клавиатур VK ------------------------------------------------------

VK_MAX_ROWS = 10
VK_MAX_PER_ROW = 5


def _rows(raw: str) -> list[list[dict]]:
    return json.loads(raw)["buttons"]


@pytest.mark.parametrize(
    "name, raw",
    [
        ("озеро", fkb.lake_keyboard()),
        ("снасть в воде", fkb.casting_keyboard()),
        ("поклёвка", fkb.bite_keyboard()),
        ("садок", fkb.bag_keyboard()),
        ("кнопка к воде", fkb.approach_lake_keyboard()),
        ("скупщик (корень)", akb.appraiser_root_keyboard()),
        ("скупщик: рыба", akb.appraiser_fish_keyboard(1234)),
        ("скупщик: рыба пусто", akb.appraiser_fish_keyboard(0)),
        ("карта со всеми кнопками", wkb.movement_keyboard(41, -41, None, has_mount=True)),
    ],
)
def test_keyboards_fit_vk_limits(name: str, raw: str) -> None:
    rows = _rows(raw)
    assert len(rows) <= VK_MAX_ROWS, f"{name}: {len(rows)} рядов"
    for row in rows:
        assert len(row) <= VK_MAX_PER_ROW, f"{name}: ряд из {len(row)} кнопок"


def test_strike_button_appears_only_with_the_bite() -> None:
    """Главное правило ловли: подсечка — реакция на событие, а не кнопка,
    которую можно нажать заранее и ждать. Пока снасть просто в воде, кнопки
    быть не должно; она приходит вместе с сообщением о поклёвке."""
    casting = [b["action"]["label"] for row in _rows(fkb.casting_keyboard()) for b in row]
    bite = [b["action"]["label"] for row in _rows(fkb.bite_keyboard()) for b in row]
    assert ft.BTN_STRIKE not in casting
    assert ft.BTN_STRIKE in bite


def test_lake_screens_always_have_a_way_out() -> None:
    """Экран озера — вложенный и заменяет клавиатуру целиком, поэтому без
    выхода игрок застрял бы у воды."""
    for raw in (fkb.lake_keyboard(), fkb.casting_keyboard(),
                fkb.bite_keyboard(), fkb.bag_keyboard()):
        labels = [b["action"]["label"] for row in _rows(raw) for b in row]
        assert ft.BTN_LEAVE_LAKE in labels


def test_approach_lake_button_is_inline() -> None:
    """Кнопка приходит ОТДЕЛЬНЫМ сообщением и не должна сносить нижнюю
    клавиатуру перемещения — значит обязана быть inline."""
    assert json.loads(fkb.approach_lake_keyboard())["inline"] is True


# --- Кнопка «К воде»: один раз на вход ----------------------------------------

def test_lake_button_is_sent_once_per_entry() -> None:
    """Кнопка приходит при входе на клетку и НЕ повторяется после действий на
    ней (исследование, событие, отдых) — иначе она засоряет чат. Вход к воде
    при этом остаётся доступен командой."""
    from bot import craft_button_state as st

    peer = 999001
    st.leave(peer, st.LAKE)

    assert st.should_send(peer, st.LAKE, 41, -41) is True
    st.mark_sent(peer, st.LAKE, 41, -41)
    # Исследование/событие/отдых на той же клетке — кнопки больше нет.
    assert st.should_send(peer, st.LAKE, 41, -41) is False


def test_lake_button_returns_after_leaving_and_coming_back() -> None:
    """«При перезаходе на локацию кнопку снова возвращать»: уход на любую
    другую клетку сбрасывает отметку."""
    from bot import craft_button_state as st

    peer = 999002
    st.leave(peer, st.LAKE)
    st.mark_sent(peer, st.LAKE, 41, -41)
    assert st.should_send(peer, st.LAKE, 41, -41) is False

    st.leave(peer, st.LAKE)  # ушёл на клетку без озера
    assert st.should_send(peer, st.LAKE, 41, -41) is True


def test_moving_between_two_lakes_shows_the_button_each_time() -> None:
    from bot import craft_button_state as st

    peer = 999003
    st.leave(peer, st.LAKE)
    st.mark_sent(peer, st.LAKE, 41, -41)
    assert st.should_send(peer, st.LAKE, 1, -2) is True
    st.mark_sent(peer, st.LAKE, 1, -2)
    assert st.should_send(peer, st.LAKE, 41, -41) is True


def test_lake_button_is_sent_only_from_cell_entry_points() -> None:
    """Вызовы обязаны стоять только там, где игрок ВХОДИТ на клетку. Если
    кнопка снова появится после сбора пепла или исхода события, правило «один
    раз на вход» держится только на памяти процесса, а это ненадёжно."""
    import inspect

    from bot.handlers import world as world_handlers

    source = inspect.getsource(world_handlers)
    entry_functions = {"show_location", "gate_exit_direction", "handle_arrival"}
    current = None
    callers = set()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("async def ", "def ")):
            current = stripped.split("(")[0].replace("async def ", "").replace("def ", "")
        if "send_cell_buttons(" in stripped and not stripped.startswith(("async def", "def")):
            callers.add(current)
        if "maybe_send_lake_button(" in stripped and not stripped.startswith(("async def", "def")):
            # Патч 104: кнопки клетки шлёт одна функция, её зовут входы.
            assert current == "send_cell_buttons", f"кнопка озера в обход входа: {current}"
    assert callers == entry_functions, f"кнопка шлётся не только на входе: {callers}"
