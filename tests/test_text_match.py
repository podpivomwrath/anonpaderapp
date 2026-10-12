"""Сопоставление текста команды без учёта регистра (2026-10-12): правило text=
пропускает «страж», и обработчик обязан найти «Страж», а не упасть."""

from bot import text_match
from bot.keyboards import world as kb
from game.world import world_config as wc
from bot.handlers.list_keeper import ALL_SUBCLASS_TITLES
from bot.onboarding_texts import CLASS_BUTTONS, REGION_BUTTONS


def test_lookup_ignores_case_and_spaces() -> None:
    assert text_match.lookup({"Страж": 1}, "  страж ") == 1
    assert text_match.lookup({"Страж": 1}, "СТРАЖ") == 1
    assert text_match.lookup({"Страж": 1}, "стража") is None
    assert text_match.canonical(["Да"], "да") == "Да"
    assert text_match.same("⚔️ Путь стали", "⚔️ путь СТАЛИ")


def test_every_menu_label_is_found_in_lower_case() -> None:
    for mapping in (ALL_SUBCLASS_TITLES, CLASS_BUTTONS, REGION_BUTTONS):
        for label, value in mapping.items():
            assert text_match.lookup(mapping, label.lower()) == value


def test_direction_resolves_from_lower_case_city_label() -> None:
    # Клетка рядом с городом: подпись кнопки - название города.
    cx, cy = next(iter(wc.CITY_COORDS.values()))
    x, y = cx - 1, cy
    labels = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        arrow = next(a for a, d in kb._DIRECTION_DELTAS.items() if d == (dx, dy))
        label = kb._direction_label(x, y, dx, dy, arrow)
        labels.append(label)
        assert kb.resolve_direction(x, y, label.lower()) == (dx, dy)
    assert any(label not in kb._DIRECTION_DELTAS for label in labels), "нет подписи-города"
