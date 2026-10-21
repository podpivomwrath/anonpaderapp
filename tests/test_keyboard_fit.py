"""Экран без прокрутки и читаемые подписи (2026-10-21, владелец: «самое
главное - чтобы не листать и читалось то, что на кнопке»).

Обходит клавиатуры города, дома, скупщика и ремёсел в худшем случае
(всё открыто, мини-апп включён) и проверяет ряды и длину подписей.
Карта движения сюда не входит: у неё свои 7 рядов, это осознанно.
"""

import json

import pytest

from bot.keyboards import appraiser as akb
from bot.keyboards import world as world_kb
from config import Settings

#: Длина подписи по числу кнопок в ряду - дальше VK режет многоточием.
MAX_LABEL = {1: 30, 2: 14, 3: 11, 4: 8}


class _Char:
    level = 60
    subclass = "guardian"
    has_house = True
    region = "ridge"


def _screens():
    from bot.handlers import house as house_handlers
    from game.economy import alchemy_config, cooking_config

    c = _Char()
    return {
        "площадь": world_kb.city_square_keyboard(c, mentor_badge=True, has_mount=True),
        "таверна": world_kb.tavern_keyboard(c, mentor_badge=True),
        "торговый квартал": world_kb.market_quarter_keyboard(),
        "дом": world_kb.house_keyboard(),
        "стол": house_handlers.alchemy_keyboard(alchemy_config.MAX_LEVEL),
        "печь": house_handlers.oven_keyboard(cooking_config.MAX_LEVEL),
        "скупщик": akb.appraiser_root_keyboard(),
    }


@pytest.fixture(autouse=True)
def _miniapp_on(monkeypatch):
    monkeypatch.setattr(world_kb, "get_settings", lambda: Settings(_env_file=None, vk_miniapp_url="https://vk.com/app1"))


def test_screens_fit_without_scroll() -> None:
    for name, raw in _screens().items():
        rows = json.loads(raw)["buttons"]
        assert len(rows) <= 5, f"{name}: {len(rows)} рядов - придётся листать"


def test_labels_fit_their_buttons() -> None:
    for name, raw in _screens().items():
        for row in json.loads(raw)["buttons"]:
            limit = MAX_LABEL.get(len(row), 6)
            for button in row:
                label = button["action"].get("label", "")
                assert len(label) <= limit, f"{name}: «{label}» длиннее {limit} при {len(row)} в ряд"
