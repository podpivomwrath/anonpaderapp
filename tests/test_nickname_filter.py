"""Фильтр мата в никах (2026-11-14, владелец: прошёл ник «ХУИЩЕ»; ещё был
«Ёбаныйрот» - «ёбан» не совпадал с «ебан»)."""

import pytest

from services.onboarding_service import contains_banned_word


@pytest.mark.parametrize("name", [
    "ХУИЩЕ", "Ёбаныйрот", "хуяк", "Хуюшка",
    "х_у_й", "Х1у1й", "ХУ_Е_ТА",
    "XYEC", "xyйня",          # латиница, похожая на кириллицу (смешение отсекает формат, но фильтр тоже)
    "huyak", "Pizdec", "Pidor777", "zalupa", "Blyat",
    "Заебатый", "Наебалово", "Жопастик", "Говнюк", "Сучка",
    "fUcKer123", "СуперХуйер",
])
def test_rude_names_are_blocked(name: str) -> None:
    assert contains_banned_word(name), name


@pytest.mark.parametrize("name", [
    "Еста", "Ёста", "Странник", "Хлебушек", "Небосвод", "Ребус", "Педро", "Мандарин",
    "Сучок", "Хутор", "Tsukasa", "Shuichi", "Lebanon", "Debater", "Mayckillo",
    "Tibialis", "Solar_Azure", "Хеймзорг", "Дедушка_Ау", "Invin", "pupsik",
    "Субару", "Ребекка", "Себастьян", "Глеб", "Убийца", "Хьюго",
])
def test_ordinary_names_pass(name: str) -> None:
    assert not contains_banned_word(name), name
