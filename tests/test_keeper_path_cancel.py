"""Выбор пути у Хранителя: с экрана выбора можно уйти (2026-11-13, владелец)."""

import json
from types import SimpleNamespace

from bot.handlers import list_keeper
from bot.keyboards.list_keeper import BTN_CANCEL_PATH, paths_keyboard


def _labels(kb_json: str) -> list[str]:
    rows = json.loads(kb_json)["buttons"]
    return [b["action"].get("label") for row in rows for b in row]


def test_paths_keyboard_always_has_cancel() -> None:
    for decline in (False, True):
        labels = _labels(paths_keyboard(["Отравитель", "Клинок теней"], decline=decline))
        assert BTN_CANCEL_PATH in labels


def test_gold_is_taken_only_on_confirm() -> None:
    """С 2026-11-13 плата - на «Да, это мой путь». Старые строки в базе
    (PATH_SELECT / PATH_CONFIRM) значат «уже заплатил» - второй раз не берём."""
    fresh = SimpleNamespace(subclass_select_state=list_keeper.STATE_OFFER, subclass_free_repick=False)
    assert not list_keeper._paid(fresh) and list_keeper._can_decline(fresh)
    assert "20 000 золота" in list_keeper._price_line(fresh)
    for state in (list_keeper.STATE_PATH_SELECT, list_keeper.STATE_PATH_CONFIRM, list_keeper.STATE_PATH_PAID):
        old = SimpleNamespace(subclass_select_state=state, subclass_free_repick=False)
        assert list_keeper._paid(old) and not list_keeper._can_decline(old)
        assert list_keeper._price_line(old) == ""


def test_paid_but_left_is_not_restored_into_the_choice() -> None:
    # Иначе после рестарта бот снова запер бы игрока в выборе пути.
    assert list_keeper.STATE_PATH_PAID not in list_keeper.RESTORE_STATES
    assert len(list_keeper.STATE_PATH_PAID) <= 32  # characters.subclass_select_state
    assert list_keeper.KEEPER["path_cancelled"].strip()
